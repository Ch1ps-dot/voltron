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
SAVED_BEST_GENERATOR:
$code
RFC_POSSIBLE_RESPONSES:
$poss_response
RUNTIME_OBSERVED_RESPONSES:
$trace

CONTRACT
The saved baseline is a generator, normally with `generate()` as its entry,
not a mutator. Return a complete, standalone Python program defining exactly
one top-level `mutate() -> bytes` with no parameters. You may reuse or replace
the baseline structure; `generate()` may remain only as a helper and must not
be the only entry point. A minimal safe conversion is:
```python
def generate() -> bytes:
    ...

def mutate() -> bytes:
    return generate()
```
- Before returning, verify that the complete candidate has that one top-level
  `mutate` definition and valid Python.
- Preserve the saved generator's state-reaching structure, then introduce controlled field-level anomalies supported by the IR.
- Each `mutate()` invocation must return exactly one complete `$msg_type` request. Do not concatenate messages, mutate into a different request type, or return a multi-message sequence.
- You may use target-specific URLs or named resources stated in SUT_CONTEXT when helpful for accessing the intended endpoint or resource.
- Prioritize RFC response types not yet present in runtime observations; avoid patterns that only repeat observed outcomes.
- Prefer mutations that pass framing and early parsing before stressing deeper validation: boundary/out-of-range numbers, inconsistent declared lengths, empty/long/invalid tokens, malformed quoting/charset, reused/duplicated IDs, unsupported versions, or compound semantic conflicts.
- Use deterministic mutation families plus bounded randomness, built-ins only, no networking/I/O, and never raise. Keep runtime practical while allowing large free-form payloads when useful.

OUTPUT
Return Python source only, without Markdown fences, JSON, patches, diffs, or
explanation. The source must define `mutate() -> bytes` and return non-empty
bytes on every invocation. Do not return only `generate()`.
