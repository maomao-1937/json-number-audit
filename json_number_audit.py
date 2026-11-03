"""Bounded, value-private JSON decimal-to-binary64 diagnostic (Python 3.11+)."""

import errno
import json
import math
import os
import re
import stat
import sys

MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 100_000
MAX_NUMBER_CHARS = 128
MAX_EXPONENT = 10_000
SAFE_INTEGER = 2**53 - 1
FLAGS = ('finite_inexact', 'overflow', 'underflow_to_zero',
         'negative_zero', 'outside_safe_integer')
RISK_FLAGS = ('finite_inexact', 'overflow', 'underflow_to_zero', 'outside_safe_integer')


class InvalidInput(ValueError):
    """Neutral boundary error; never attach caller text."""


class Number:
    """A parser number token, deliberately distinct from strings and integers."""
    __slots__ = ('token',)

    def __init__(self, token):
        self.token = token


def validate_path(path):
    """Reject URI/device/ADS syntax before any filesystem operation."""
    if not isinstance(path, str) or not path or path == '-' or '\x00' in path:
        raise InvalidInput()
    normalized = path.replace('/', '\\')
    if normalized.startswith(('\\\\', '\\??\\')):
        raise InvalidInput()
    drive_absolute = re.match(r'^[A-Za-z]:\\', normalized) is not None
    remainder = normalized[2:] if drive_absolute else normalized
    if ':' in remainder or '?' in normalized or '*' in normalized:
        raise InvalidInput()
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$', 'CONIN$', 'CONOUT$'}
    reserved.update(prefix + digit for prefix in ('COM', 'LPT') for digit in '123456789¹²³')
    for component in remainder.split('\\'):
        basename = component.rstrip(' .').split('.', 1)[0].rstrip(' .').upper()
        if basename in reserved:
            raise InvalidInput()


def read_input(path):
    validate_path(path)
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise InvalidInput()
    # Nonblocking is effective on POSIX if a special file replaces the stat target.
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise InvalidInput()
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise InvalidInput()
    return raw.decode('utf-8-sig', errors='strict')


def exponent_of(token):
    parts = re.split('[eE]', token, maxsplit=1)
    if len(parts) == 1:
        return 0
    exponent = parts[1]
    digits = exponent.lstrip('+-').lstrip('0') or '0'
    # Bound before int or power; a huge exponent string never becomes an integer.
    if len(digits) > 5 or (len(digits) == 5 and digits > '10000'):
        raise InvalidInput()
    value = int(digits)
    return -value if exponent.startswith('-') else value


def check_depth(text):
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > MAX_DEPTH:
                raise InvalidInput()
        elif char in ']}':
            depth -= 1


def parse_document(text):
    check_depth(text)
    numbers = []

    def number(token):
        if len(token) > MAX_NUMBER_CHARS or len(numbers) >= MAX_NODES:
            raise InvalidInput()
        exponent_of(token)
        item = Number(token)
        numbers.append(item)
        return item

    def constant(_token):
        raise InvalidInput()

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InvalidInput()
            result[key] = value
        return result

    root = json.loads(text, parse_int=number, parse_float=number,
                      parse_constant=constant, object_pairs_hook=object_pairs)
    pending = [root]
    count = 0
    while pending:
        value = pending.pop()
        count += 1
        if count > MAX_NODES:
            raise InvalidInput()
        if isinstance(value, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                raise InvalidInput()
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
    return numbers


def analyze(number, ordinal):
    token = number.token
    exponent = exponent_of(token)
    mantissa = re.split('[eE]', token, maxsplit=1)[0]
    sign = -1 if mantissa.startswith('-') else 1
    unsigned = mantissa.lstrip('-')
    whole, separator, fraction = unsigned.partition('.')
    coefficient = int(whole + fraction)
    scale = exponent - len(fraction)
    numerator = sign * coefficient * (10**scale if scale >= 0 else 1)
    denominator = 10**(-scale) if scale < 0 else 1
    converted = float(token)
    overflow = not math.isfinite(converted)
    underflow = numerator != 0 and converted == 0.0
    inexact = False
    if not overflow and not underflow:
        binary_numerator, binary_denominator = converted.as_integer_ratio()
        inexact = numerator * binary_denominator != binary_numerator * denominator
    outside = numerator % denominator == 0 and abs(numerator) > SAFE_INTEGER * denominator
    row = {
        'ordinal': ordinal,
        'kind': 'exponent' if 'e' in token.lower() else ('decimal' if separator else 'integer'),
        'finite_inexact': inexact,
        'overflow': overflow,
        'underflow_to_zero': underflow,
        'negative_zero': sign < 0 and coefficient == 0,
        'outside_safe_integer': outside,
    }
    row['codes'] = [flag for flag in FLAGS if row[flag]]
    return row


def audit(text):
    rows = [analyze(number, ordinal) for ordinal, number in enumerate(parse_document(text), 1)]
    risks = sum(any(row[flag] for flag in RISK_FLAGS) for row in rows)
    return {'number_count': len(rows), 'risk_count': risks,
            'counts': {flag: sum(row[flag] for row in rows) for flag in FLAGS}, 'numbers': rows}


def emit(text):
    """Write without buffered stdout, avoiding shutdown flush failures/exit 120."""
    data = (text + '\n').encode('ascii')
    try:
        offset = 0
        while offset < len(data):
            written = os.write(sys.stdout.fileno(), data[offset:])
            if not written:
                return False
            offset += written
    except OSError as error:
        if isinstance(error, BrokenPipeError) or error.errno in (errno.EPIPE, errno.EBADF, errno.EINVAL):
            return False
        raise
    return True


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args in (['--help'], ['-h']):
        try:
            emit('Usage: python json_number_audit.py INPUT\n'
                 'Read a bounded UTF-8 JSON file; emit value-private binary64 findings.\n'
                 'Exit: 0 clean, 1 numeric risks, 2 invalid/unsupported/operational.\n'
                 'Closed stdout exits 0.')
        except OSError:
            return 2
        return 0
    try:
        if len(args) != 1 or args[0].startswith('-'):
            raise InvalidInput()
        report = audit(read_input(args[0]))
        code = 1 if report['risk_count'] else 0
    except (InvalidInput, OSError, UnicodeError, ValueError, RecursionError, OverflowError):
        report = {'error': 'invalid_input'}
        code = 2
    try:
        return code if emit(json.dumps(report, separators=(',', ':'), ensure_ascii=True)) else 0
    except OSError:
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
