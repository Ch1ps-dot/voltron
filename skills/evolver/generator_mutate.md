SCOPE
Authorized controlled fuzz testing only.

TASK
Generate one structured mutation that reaches deep parser/state validation and explores an RFC outcome not yet observed.

INPUT
PROTOCOL: $pro_name
TYPE_FIELD: $field_name
REQUEST_TYPE: $msg_type
IR_FIELD_TABLE_JSON:
$msg_ir
SUT_CONTEXT:
$info
BASE_SHA256: $base_sha256
NUMBERED_SAVED_BEST_GENERATOR:
$code
RFC_POSSIBLE_RESPONSES:
$poss_response
RUNTIME_OBSERVED_RESPONSES:
$trace

CONTRACT
The numbered baseline is a generator, normally with `generate()` as its entry,
not a mutator. For every `patch`, the final candidate must define exactly one
top-level `mutate() -> bytes` with no parameters. Replace `generate()` or keep
it only as a helper; it must not remain the only entry point. A minimal safe
conversion is:
```python
def generate() -> bytes:
    ...

def mutate() -> bytes:
    return generate()
```
- Before returning a patch, verify that its changed ranges leave the complete
  candidate with that one top-level `mutate` definition and valid Python.
- Preserve the saved generator's state-reaching structure, then introduce controlled field-level anomalies supported by the IR.
- You may use target-specific URLs or named resources stated in SUT_CONTEXT when helpful for accessing the intended endpoint or resource.
- Prioritize RFC response types not yet present in runtime observations; avoid patterns that only repeat observed outcomes.
- Prefer mutations that pass framing and early parsing before stressing deeper validation: boundary/out-of-range numbers, inconsistent declared lengths, empty/long/invalid tokens, malformed quoting/charset, reused/duplicated IDs, unsupported versions, or compound semantic conflicts.
- Use deterministic mutation families plus bounded randomness, built-ins only, no networking/I/O, and never raise. Keep runtime practical while allowing large free-form payloads when useful.

OUTPUT
JSON only. For a change, return {"base_sha256":"$base_sha256","action":"patch","edits":[{"start_line":1,"end_line":1,"replacement":"changed source lines"}]}.
If no evidence-backed mutation can safely improve on the saved generator, return {"base_sha256":"$base_sha256","action":"no_change","reason":"already_satisfies_goal|insufficient_evidence|no_safe_change","edits":[]}; do not return a patch that leaves only `generate()`.
Line ranges are one-based, inclusive, non-overlapping, and refer to NUMBERED_SAVED_BEST_GENERATOR. For patch, return only changed ranges, never the full program. Replacement must contain exact Python including indentation and escaped newlines.
