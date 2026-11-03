# Testing

Actual local run on 2026-11-03: Python 3.11.15 (MSC v.1944, AMD64), Microsoft Windows 10.0.26300. From repository root:

```console
python -B -m unittest discover -s tests -v
```

Before the implementation existed: **17 tests, 31 assertion failures, zero errors** (2.343 seconds), asserting the missing CLI behavior and implementation. After implementation: **17 tests passed** (4.630 seconds). Builder RED/GREEN logs are retained in the parent release evidence outside the publishable source tree. The failures were actually observed before adding production code; no failing run is inferred from a later test suite.

A focused preaccess UNC regression was then added before its fix: **18 tests, four assertion failures** (4.557 seconds), one for each ordinary or mixed-separator UNC spelling reaching stat. After rejecting normalized UNC prefixes: **18 tests passed** (4.459 seconds). Logs: `red-unc.txt` and `green-unc.txt` in parent builder evidence. Both stat and open are guarded by the regression.

Independent quality review identified an unhandled operational stdout error in the help branch. A regression first injected `OSError(errno.EIO)` for help, argument-error output and normal audit output: **19 tests, one assertion failure** (4.583 seconds), because help propagated the exception. After handling that error: **19 tests passed** (4.807 seconds). Logs: `red-help-output.txt` and `green-help-output.txt` in parent builder evidence. Operational write failures now return 2 for all three output paths; the existing real closed-pipe tests still return 0 without stderr.

The suite tests exact `Fraction(Decimal(token))` comparison against `Fraction.from_float`, safe-integer edges and exactly representable out-of-range integers, integral exponent spellings, original token kinds and encounter order, overflow/underflow, lexical negative zero, duplicate decoded keys, malformed JSON, UTF-8/BOM/surrogates, no value/key leakage, byte/depth/node/token/exponent boundaries, argument and filesystem error neutrality, path refusal before stat, read-only source preservation, and real `os.pipe` closed-reader handling for both normal output and help.

CLI subprocess tests use the script basename from the repository root and an eight-second timeout. Tests create only temporary synthetic files and compare bytes before/after. The path preaccess test mocks stat solely to establish refusal happens before filesystem access. These checks do not certify all symlink races, remote filesystem backing or arbitrary operating systems.

Runnable synthetic smoke cases and expected exit codes are listed in [checks.json](checks.json): clean (0), numeric risks (1), informational negative zero (0), duplicate-key input (2), help (0). All example data is synthetic. Run each command from the repository root with `python` before the argument list. CI added by the release coordinator provides additional platform evidence; it is distinct from this local verification.
