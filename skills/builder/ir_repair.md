TASK
Repair protoIR syntax without changing protocol semantics.

INPUT
SOURCE_IR (XML or compact field table):
$ir
ERRORS:
$error

CONTRACT
- Preserve message/field names, order, constant values, variable ranges, intent, and existing comments.
- Fix only reported XML/attribute errors: malformed tags, missing mandatory attributes, duplicate/invalid labels, `constant`/`variable` typos, and length units (`B`, `b`, `undefined`).
- Add a missing required attribute or comment only from existing evidence; do not invent semantics.
- The repaired artifact is one message only. The root element MUST be `<message>`;
  never emit an `<ir>`, `<protoIR>`, `<root>`, Markdown fence, or explanatory wrapper.
- Emit `<message>` with every field containing `name`, `type`, `length`, and `value`.

OUTPUT
Well-formed protoIR XML only; no Markdown or prose.
