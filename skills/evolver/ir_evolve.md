TASK
Repair an IR whose model-learning feedback indicates an incomplete or inaccurate message definition.

INPUT
PROTOCOL: $pro_name
DIRECTION: $direction
MESSAGE_TYPE: $msg_type
BASE_SHA256: $base_sha256
CURRENT_IR_FIELD_TABLE_JSON:
$current_ir
TYPE_RULE:
$type_rule
SPEC_CONTEXT:
$section_context
LEARNING_FEEDBACK:
$feedback

CONTRACT
- Change the IR only where feedback plus spec/type-rule evidence supports it.
- May correct order, constants, lengths, encoding, delimiters, optional/conditional/repeated fields, or payload boundaries.
- Preserve correct fields/comments and message intent. Do not invent unsupported constraints.

OUTPUT
JSON only: {"base_sha256":"$base_sha256","ops":[]}.
Use only these operations:
- update_message: message, set, remove
- insert_message: index, value={attributes,note,fields:[{attributes,note}]}
- delete_message or move_message: message, and index for move
- set_message_note: message, note
- update_field: message, field, set, remove
- insert_field: message, index, attributes, optional note
- delete_field or move_field: message, field, and index for move
- set_field_note: message, field, note
Indexes are zero-based final field/message positions. Emit only necessary operations; never repeat the full XML or field table.
