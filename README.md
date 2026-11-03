# json-number-audit

[![tests](https://github.com/maomao-1937/json-number-audit/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/json-number-audit/actions/workflows/tests.yml)

Find JSON numbers that change when handed to a binary64 consumer. Reports use numeric encounter ordinals and fixed flags, without exposing tokens, values, object keys, paths or snippets. [中文说明](README.zh-CN.md)

For example, `9007199254740992` is exactly representable as binary64 but lies outside the interoperable safe-integer range. The tool flags that range risk separately from rounding. Mathematical integers written as `1e3` or `1.0` receive the same integer-range check.

## Install from source and run

Requires Python 3.11+ with its standard library. There are no third-party dependencies, API keys, services, configuration files, environment variables or package-install steps. Download/extract this repository or clone it, change into its root, then run:

```console
python json_number_audit.py examples/clean.json
python json_number_audit.py examples/risks.json
python json_number_audit.py examples/negative-zero.json
python json_number_audit.py --help
python -B -m unittest discover -s tests -v
```

On Windows, `py -3.11` can replace `python` when installed. The input is one named regular file, read in binary mode and decoded as strict UTF-8. One initial UTF-8 BOM is accepted and counts toward the byte limit. Standard input, URLs, and multiple JSON documents are unsupported. Top-level scalar JSON is accepted. Duplicate decoded object keys, NaN/Infinity, invalid Unicode and unpaired surrogate code points in keys or values are rejected. A valid escaped surrogate pair is accepted.

## Output and exit codes

Standard output is one compact JSON object plus a newline; standard error is empty. Every numeric token gets a row in lexical/parser encounter order, starting at ordinal 1. `kind` is `integer`, `decimal` or `exponent` according to the original spelling. Boolean flags and identically named entries in `codes` mean:

| Flag | Meaning |
| --- | --- |
| `finite_inexact` | Nonzero finite binary64 result differs from the exact decimal rational; excludes underflow to zero. |
| `overflow` | Conversion produces positive or negative infinity. |
| `underflow_to_zero` | An exact nonzero decimal converts to either sign of zero. |
| `negative_zero` | Exact value is zero and the original token has a minus sign. Informational. |
| `outside_safe_integer` | Exact value is an integer outside `[-9007199254740991,9007199254740991]`, including exponent/decimal spellings. |

`number_count` counts all rows. `risk_count` counts rows with any flag except `negative_zero`; multiple flags on one row count once. `counts` gives each flag's row count. An empty/non-numeric document has zero rows. For `0.1` the single row is:

```json
{"ordinal":1,"kind":"decimal","finite_inexact":true,"overflow":false,"underflow_to_zero":false,"negative_zero":false,"outside_safe_integer":false,"codes":["finite_inexact"]}
```

Exit `0`: no numeric risks (negative zero alone is informational). Exit `1`: at least one numeric risk. Exit `2`: invalid, unsupported, unavailable or unreadable input; the fixed report is `{"error":"invalid_input"}`. Closed stdout, including `--help`, exits `0` quietly; this is an intentional pipeline exception and does not establish a successful audit.

## Bounds and path profile

Limits are fixed in source, with no runtime overrides:

| Resource | Maximum |
| --- | --- |
| Input bytes, including BOM | 2 MiB (2,097,152 bytes) |
| Nested array/object containers | 64 |
| Parsed nodes, including root, all values and object keys | 100,000 |
| Original numeric token length | 128 ASCII characters |
| Absolute explicit decimal exponent | 10,000 |

Exponent magnitude is checked as bounded text before integer/power construction. Thus `1e999` and `1e-999` are analyzable, while `1e10001` is refused. Leading zeroes in an exponent do not change its magnitude. The fractional digit count can add at most the bounded token length to the rational denominator exponent. Exact comparison uses integer ratios and cross multiplication; it does not depend on a Decimal arithmetic precision context. `parse_int` and `parse_float` first retain distinct original-token objects; binary64 conversion happens only during analysis.

Before stat/open, a conservative cross-platform path profile rejects URI schemes and colon syntax except absolute Windows drive paths, drive-relative paths, ADS syntax, UNC/network paths (including mixed separators), device prefixes, wildcards, and reserved/unsupported basename spellings. The latter includes CON/PRN/AUX/NUL, CLOCK$/CONIN$/CONOUT$, COM/LPT 1–9 (and superscript 1–3), case-insensitively, with spaces/dots trimmed before extensions. These are profile refusals, not a claim that every spelling resolves to an OS device on every system. Absolute Windows drive paths are allowed. Use `./` for a filename starting with `-`.

Only regular files are read, with size checked during a bounded read. Symlinks are followed; regular-file checks do not prove physically local backing. Mounts and symlink targets can refer to remote storage despite lexical UNC rejection; use a trusted local directory if that matters. There are no network client calls, subprocesses, database operations, or file writes in the product. Output is written to stdout. Tests use subprocesses and temporary synthetic files.

## Scope and evidence

This diagnoses CPython's binary64 conversion on the verified environment. It does not predict every language/runtime, validate schemas, canonicalize JSON, certify monetary safety or prove a downstream application loses data. A runtime retaining decimal/big-integer values may preserve numbers that this policy flags. Negative zero detection describes lexical input sign, separately from nonzero negative underflow.

Verified on Python 3.11.15, 64-bit AMD64, Microsoft Windows 10.0.26300, on 2026-11-03. The 19-test suite includes independent `Fraction(Decimal(token))` comparisons, read-only checks, limits, privacy, operational output failures and real closed stdout pipes. See [TESTING.md](TESTING.md) for actual commands and [RESEARCH.md](RESEARCH.md) for sources, alternatives and inference boundaries. Other OS/Python versions are intended compatibility, not claimed local verification. MIT licensed.
