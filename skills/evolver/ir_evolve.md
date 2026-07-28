You are an expert in protocol specification analysis and protoIR repair.

The fuzzer is in the model learning phase. It has observed repeated generator
or parser failures that may be caused by an incomplete or inaccurate protoIR
message description.

## Input

- Protocol name: $pro_name
- Message direction: $direction
- Target message type: $msg_type
- Current protoIR:

```xml
$current_ir
```

- Type rule:

$type_rule

- Relevant specification sections:

$section_context

- Feedback from model learning:

$feedback

## Task

Repair the protoIR only when the feedback and specification context indicate
that the current IR is incomplete or inconsistent with the protocol. The repair
may adjust field order, constants, lengths, encodings, delimiters, optional or
conditional fields, repeated fields, or payload boundaries.

## Constraints

- Preserve all correct fields and comments.
- Do not invent fields or constraints unsupported by the specification context,
  type rule, or concrete feedback.
- Keep the target message type semantic intent unchanged.
- Return one valid, well-formed XML fragment or document.
- Do not include Markdown fences, explanations, or prose.
