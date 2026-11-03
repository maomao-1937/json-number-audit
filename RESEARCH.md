# Research and differentiation

Primary sources checked 2026-11-03 before documentation freeze. This project contains original bounded diagnostic logic; it does not copy an upstream implementation.

## Documented facts

- [RFC 8259, section 6](https://www.rfc-editor.org/rfc/rfc8259#section-6) describes the JSON number grammar and binary64 interoperability guidance, including the interoperable integer interval from -(2^53)+1 to (2^53)-1. That interval is a range guarantee; integers outside it can still individually be exactly representable.
- [Python 3.11 json](https://docs.python.org/3.11/library/json.html) supports `parse_int`, `parse_float`, `parse_constant` and `object_pairs_hook`. Its default acceptance of duplicate names and nonfinite constants motivates explicit refusal here. Its documentation recommends limiting untrusted input size.
- [Python 3.11 Decimal](https://docs.python.org/3.11/library/decimal.html) distinguishes exact decimal construction and context-sensitive arithmetic. The tests use exact `Decimal` construction followed by `Fraction`; production uses bounded integer arithmetic so no Decimal arithmetic context can round its comparison.
- [jq manual](https://jqlang.org/manual/) documents a general JSON filter language and numeric behavior, including build/version considerations. It is a mature alternative for broad extraction, transformation and validation tasks; those capabilities exceed this tool's scope.

## Design inference

A report identifying numeric ordinals and fixed risk classes may help inspect API/model JSON handoffs without disclosing application keys or numeric values. This usefulness is a design inference: there is no measured adoption, user study, time-saving result or cross-language compatibility claim. Ordinals/counts/kinds themselves reveal structural metadata; this is value minimization, not an anonymization guarantee.

The safe-integer flag is a deliberately conservative policy even when conversion is exact. Negative zero is informational. Rejecting duplicate keys avoids selecting one competing numeric value silently. The fixed byte/depth/node/token/exponent limits bound supported work, rather than claiming general hostile-input security.

## Fair alternatives and boundaries

Use jq for general transformations and its documented numeric model; use a decimal or arbitrary-precision parser directly when the consumer can preserve exact values; use actual target-runtime integration tests to establish downstream behavior. This tool is narrower: a source-only, standard-library CLI comparing every bounded JSON numeric token with binary64, without values in its report. It neither transforms data nor validates schemas, canonicalization, monetary correctness, all runtimes or a specific application's behavior.
