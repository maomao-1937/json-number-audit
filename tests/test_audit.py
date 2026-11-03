import importlib.util
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from fractions import Fraction
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'json_number_audit.py'


class AuditTests(unittest.TestCase):
    def run_cli(self, raw, expected=0):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            source.write_bytes(raw if isinstance(raw, bytes) else raw.encode('utf-8'))
            before = source.read_bytes()
            result = subprocess.run([sys.executable, '-B', SCRIPT.name, str(source)],
                                    cwd=ROOT, capture_output=True, timeout=8)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual(result.stderr, b'')
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [source])
            return json.loads(result.stdout)

    def test_exact_clean(self):
        report = self.run_cli('[0,0.5,9007199254740991,1e3]')
        self.assertEqual(report['number_count'], 4)
        self.assertEqual(report['risk_count'], 0)
        self.assertEqual([x['kind'] for x in report['numbers']],
                         ['integer', 'decimal', 'integer', 'exponent'])

    def test_exact_rational_oracle(self):
        tokens = ['0.1', '0.5', '1.25', '1e-10', '9007199254740992',
                  '9007199254740993', '-9007199254740992', '12345e-2',
                  '1.0000000000000000000000001', '90071992547409910e-1']
        report = self.run_cli('[' + ','.join(tokens) + ']', 1)
        for token, row in zip(tokens, report['numbers']):
            exact = Fraction(Decimal(token))
            self.assertEqual(row['finite_inexact'], exact != Fraction.from_float(float(token)))
            self.assertEqual(row['outside_safe_integer'],
                             exact.denominator == 1 and abs(exact.numerator) > 2**53 - 1)

    def test_exact_outside_is_not_rounded(self):
        rows = self.run_cli('[9007199254740992,9007199254740993]', 1)['numbers']
        self.assertFalse(rows[0]['finite_inexact'])
        self.assertTrue(rows[0]['outside_safe_integer'])
        self.assertTrue(rows[1]['finite_inexact'])

    def test_overflow_underflow(self):
        rows = self.run_cli('[1e309,-1e999,1e-999,-1e-999]', 1)['numbers']
        self.assertTrue(rows[0]['overflow'])
        self.assertTrue(rows[1]['overflow'])
        self.assertTrue(rows[2]['underflow_to_zero'])
        self.assertTrue(rows[3]['underflow_to_zero'])
        self.assertTrue(all(not row['finite_inexact'] for row in rows))

    def test_negative_zero_informational(self):
        report = self.run_cli('[-0,-0.0,-0e999,0,0.0]')
        self.assertEqual([row['negative_zero'] for row in report['numbers']],
                         [True, True, True, False, False])
        self.assertEqual(report['risk_count'], 0)

    def test_parser_encounter_order_privacy(self):
        report = self.run_cli('{"secret-key":[0.1,{"hidden":0.5}],"password":9007199254740993}', 1)
        self.assertEqual([row['ordinal'] for row in report['numbers']], [1, 2, 3])
        text = json.dumps(report)
        for secret in ['secret-key', 'hidden', 'password', '9007199254740993', '0.1', '0.5']:
            self.assertNotIn(secret, text)
        self.assertEqual(set(report['numbers'][0]), {'ordinal', 'kind', 'finite_inexact',
                         'overflow', 'underflow_to_zero', 'negative_zero',
                         'outside_safe_integer', 'codes'})

    def test_strict_invalid(self):
        for raw in ['{"secret":1,"secret":2}', '{"a":0,"\\u0061":1}',
                    '[NaN]', '[Infinity]', '[-Infinity]', '[01]', '[1,]',
                    '1 2', '[+1]', '[1.]', '"\\ud800"', '{"\\udfff":0}',
                    '["\\ud800",1]', '"raw\x00secret"', '']:
            with self.subTest(raw=raw):
                report = self.run_cli(raw, 2)
                self.assertEqual(report, {'error': 'invalid_input'})

    def test_utf8_bom_and_surrogate_pair(self):
        self.run_cli(b'\xef\xbb\xbf{"pair":"\\ud83d\\ude00","n":0.5}')
        self.run_cli(b'\xff[1]', 2)
        self.run_cli(b'\xef\xbb\xbf\xef\xbb\xbf[1]', 2)

    def test_no_numbers(self):
        report = self.run_cli('{"message":"ok","bool":true,"n":null}')
        self.assertEqual(report['numbers'], [])

    def test_depth_limit(self):
        self.run_cli('[' * 64 + '0' + ']' * 64)
        self.run_cli('[' * 65 + '0' + ']' * 65, 2)
        self.run_cli(json.dumps('[' * 100 + ']' * 100))

    def test_number_length_and_exponent_limits(self):
        self.run_cli('1' * 128, 1)
        self.run_cli('1' * 129, 2)
        self.run_cli('1e10000', 1)
        self.run_cli('1e-10000', 1)
        self.run_cli('1e10001', 2)
        self.run_cli('1e-10001', 2)
        self.run_cli('0e' + '9' * 100, 2)
        self.run_cli('1e' + '0' * 100 + '1')

    def test_byte_and_node_limits(self):
        self.run_cli('"' + 'a' * (2 * 1024 * 1024 - 2) + '"')
        self.run_cli('"' + 'a' * (2 * 1024 * 1024 - 1) + '"', 2)
        self.run_cli('[' + ','.join(['null'] * 99999) + ']')
        self.run_cli('[' + ','.join(['null'] * 100000) + ']', 2)

    def test_argument_errors_neutral(self):
        for args in [[], ['--unknown-secret'], ['one-secret', 'two-secret'], ['-']]:
            result = subprocess.run([sys.executable, '-B', SCRIPT.name, *args],
                                    cwd=ROOT, capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, b'')
            self.assertEqual(json.loads(result.stdout), {'error': 'invalid_input'})

    def test_missing_file_and_directory_neutral(self):
        for path in ['does-not-exist-secret.json', str(ROOT)]:
            result = subprocess.run([sys.executable, '-B', SCRIPT.name, path], cwd=ROOT,
                                    capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, b'')
            self.assertEqual(json.loads(result.stdout), {'error': 'invalid_input'})

    def test_lexical_path_rejection_before_access(self):
        self.assertTrue(SCRIPT.exists(), 'implementation required')
        spec = importlib.util.spec_from_file_location('audit_under_test', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for path in ['https://secret/input.json', 'file:///secret', 'C:relative',
                     'input.json:secret', 'NUL', 'con.txt', 'x/COM1.json',
                     '\\\\?\\C:\\secret', '//./NUL', '/\\?\\C:/secret',
                     '\\??\\C:\\secret', 'x/LPT¹.txt', 'NUL .csv',
                     'CON .json', 'dir/COM1 .txt', 'CLOCK$', 'CONIN$', 'CONOUT$']:
            with self.subTest(path=path), patch.object(module.os, 'stat', side_effect=AssertionError('access')):
                with self.assertRaises(module.InvalidInput):
                    module.read_input(path)

    def test_read_only_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'private.json'
            source.write_text('[0.5]', encoding='utf-8')
            source.chmod(0o444)
            try:
                result = subprocess.run([sys.executable, '-B', SCRIPT.name, str(source)],
                                        cwd=ROOT, capture_output=True, timeout=8)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(source.read_text(), '[0.5]')
            finally:
                source.chmod(0o644)

    def test_unc_forms_rejected_before_stat_or_open(self):
        spec = importlib.util.spec_from_file_location('audit_unc_test', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for path in ['\\\\server\\share', '//server/share', '/\\server/share', '\\/server/share']:
            with self.subTest(path=path), \
                    patch.object(module.os, 'stat', side_effect=AssertionError('stat access')), \
                    patch.object(module.os, 'open', side_effect=AssertionError('open access')):
                with self.assertRaises(module.InvalidInput):
                    module.read_input(path)

    def test_real_closed_stdout_including_help(self):
        self.assertTrue(SCRIPT.exists(), 'implementation required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'clean.json'
            source.write_text('[0.5]', encoding='utf-8')
            for args in [['--help'], [str(source)], ['--secret-invalid']]:
                reader, writer = os.pipe()
                os.close(reader)
                try:
                    result = subprocess.run([sys.executable, '-B', SCRIPT.name, *args],
                                            cwd=ROOT, stdout=writer, stderr=subprocess.PIPE, timeout=8)
                finally:
                    os.close(writer)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, b'')

    def test_output_device_failure_returns_two_for_help_and_normal_output(self):
        spec = importlib.util.spec_from_file_location('audit_output_test', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for args in [['--help'], ['--unknown'], [str(ROOT / 'examples' / 'clean.json')]]:
            with self.subTest(args=args), \
                    patch.object(module.os, 'write', side_effect=OSError(errno.EIO, 'synthetic output device failure')):
                try:
                    result = module.main(args)
                except OSError:
                    self.fail('operational output failure escaped main instead of returning 2')
                self.assertEqual(result, 2)


if __name__ == '__main__':
    unittest.main()
