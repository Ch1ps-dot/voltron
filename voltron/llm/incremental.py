"""Apply compact, model-produced deltas to generated source and protoIR."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from lxml import etree


class IncrementalOutputError(ValueError):
    """Raised when a model delta is malformed or targets the wrong baseline."""


class SourceDeltaResult(str):
    """A source-delta application result that preserves string compatibility."""

    changed: bool
    reason: str | None

    def __new__(
        cls,
        source: str,
        *,
        changed: bool,
        reason: str | None = None,
    ) -> "SourceDeltaResult":
        result = super().__new__(cls, source)
        result.changed = changed
        result.reason = reason
        return result

    def __getnewargs_ex__(self):
        return (
            (str(self),),
            {"changed": self.changed, "reason": self.reason},
        )


NO_CHANGE_REASONS = frozenset({
    "already_satisfies_goal",
    "insufficient_evidence",
    "no_safe_change",
})


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def parse_json_artifact(response: str | None) -> dict[str, Any]:
    """Extract one JSON object while tolerating an accidental Markdown fence."""
    if not response:
        raise IncrementalOutputError("empty incremental response")
    cleaned = re.sub(
        r"^\s*```(?:json)?\s*|\s*```\s*$",
        "",
        response.strip(),
        flags=re.IGNORECASE,
    )
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise IncrementalOutputError(
            f"incremental response is not valid JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise IncrementalOutputError("incremental response must be a JSON object")
    return value


def numbered_source_context(source: str, max_chars: int = 12_000) -> str:
    """Render source with stable one-based line numbers under a context budget."""
    max_chars = max(512, int(max_chars))
    lines = source.splitlines()
    width = max(1, len(str(max(1, len(lines)))))
    line_limit = max(64, min(256, max_chars // 3))
    rendered = []
    for number, line in enumerate(lines, start=1):
        prefix = f"{number:0{width}d}|"
        if len(prefix) + len(line) > line_limit:
            marker = "[... line truncated ...]"
            retained = max(2, line_limit - len(prefix) - len(marker))
            head = retained * 2 // 3
            line = f"{line[:head]}{marker}{line[-(retained - head):]}"
        rendered.append(f"{prefix}{line}")
    complete = "\n".join(rendered)
    if len(complete) <= max_chars:
        return complete

    marker_reserve = 80
    head_budget = (max_chars - marker_reserve) * 2 // 3
    tail_budget = max_chars - marker_reserve - head_budget
    head: list[str] = []
    head_size = 0
    for line in rendered:
        size = len(line) + 1
        if head and head_size + size > head_budget:
            break
        head.append(line)
        head_size += size

    tail: list[str] = []
    tail_size = 0
    for line in reversed(rendered[len(head):]):
        size = len(line) + 1
        if tail and tail_size + size > tail_budget:
            break
        tail.append(line)
        tail_size += size
    tail.reverse()

    first_omitted = len(head) + 1
    last_omitted = len(rendered) - len(tail)
    marker = f"... omitted source lines {first_omitted}-{last_omitted} ..."
    return "\n".join([*head, marker, *tail])


def apply_source_delta(source: str, delta: dict[str, Any]) -> SourceDeltaResult:
    """Apply a validated source delta or preserve its verified baseline."""
    expected_hash = content_sha256(source)
    if delta.get("base_sha256") != expected_hash:
        raise IncrementalOutputError("source delta base_sha256 mismatch")
    edits = delta.get("edits")
    action = delta.get("action", "patch")
    if action == "no_change":
        reason = delta.get("reason")
        if edits != []:
            raise IncrementalOutputError("source delta no_change requires empty edits")
        if reason not in NO_CHANGE_REASONS:
            raise IncrementalOutputError("source delta no_change has an invalid reason")
        return SourceDeltaResult(source, changed=False, reason=reason)
    if action != "patch":
        raise IncrementalOutputError("source delta action must be patch or no_change")
    if not isinstance(edits, list) or not edits:
        raise IncrementalOutputError("source delta patch requires a non-empty edits list")

    lines = source.splitlines(keepends=True)
    if not lines:
        raise IncrementalOutputError("cannot patch empty source")
    normalized: list[tuple[int, int, str]] = []
    for item in edits:
        if not isinstance(item, dict):
            raise IncrementalOutputError("each source edit must be an object")
        start = item.get("start_line")
        end = item.get("end_line")
        replacement = item.get("replacement")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(replacement, str)
        ):
            raise IncrementalOutputError(
                "source edit requires integer start_line/end_line and string replacement"
            )
        if start < 1 or end < start or end > len(lines):
            raise IncrementalOutputError(
                f"source edit range {start}-{end} is outside 1-{len(lines)}"
            )
        normalized.append((start, end, replacement))

    normalized.sort(key=lambda edit: edit[0])
    previous_end = 0
    for start, end, _replacement in normalized:
        if start <= previous_end:
            raise IncrementalOutputError("source edit ranges overlap")
        previous_end = end

    newline = "\r\n" if "\r\n" in source else "\n"
    source_has_final_newline = source.endswith(("\n", "\r"))
    for start, end, replacement in reversed(normalized):
        must_end_line = end < len(lines) or (
            end == len(lines) and source_has_final_newline
        )
        if replacement and must_end_line and not replacement.endswith(("\n", "\r")):
            replacement += newline
        lines[start - 1:end] = [replacement] if replacement else []

    evolved = "".join(lines)
    if evolved == source:
        raise IncrementalOutputError("source delta made no change")
    return SourceDeltaResult(evolved, changed=True)


def _messages(root) -> list:
    if root.tag == "message":
        return [root]
    if root.tag == "ir":
        return list(root.findall(".//message"))
    raise IncrementalOutputError(f"unsupported protoIR root: {root.tag}")


def _find_message(root, name: Any):
    if not isinstance(name, str) or not name:
        raise IncrementalOutputError("IR operation requires message")
    matches = [message for message in _messages(root) if message.get("name") == name]
    if len(matches) != 1:
        raise IncrementalOutputError(
            f"IR message {name!r} matched {len(matches)} elements"
        )
    return matches[0]


def _find_field(message, name: Any):
    if not isinstance(name, str) or not name:
        raise IncrementalOutputError("IR field operation requires field")
    matches = [field for field in message.findall("field") if field.get("name") == name]
    if len(matches) != 1:
        raise IncrementalOutputError(
            f"IR field {name!r} matched {len(matches)} elements"
        )
    return matches[0]


def _attribute_changes(element, operation: dict[str, Any]) -> None:
    changes = operation.get("set", {})
    removals = operation.get("remove", [])
    if not isinstance(changes, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in changes.items()
    ):
        raise IncrementalOutputError("IR set must be a string-to-string object")
    if not isinstance(removals, list) or not all(
        isinstance(key, str) for key in removals
    ):
        raise IncrementalOutputError("IR remove must be a string array")
    for key in removals:
        element.attrib.pop(key, None)
    for key, value in changes.items():
        element.set(key, value)


def _following_comments(parent, element) -> list:
    children = list(parent)
    index = children.index(element) + 1
    comments = []
    while index < len(children) and children[index].tag is etree.Comment:
        comments.append(children[index])
        index += 1
    return comments


def _set_note(parent, element, note: Any) -> None:
    if not isinstance(note, str):
        raise IncrementalOutputError("IR note must be a string")
    comments = _following_comments(parent, element)
    if note:
        if comments:
            comments[0].text = note
            for comment in comments[1:]:
                parent.remove(comment)
        else:
            parent.insert(parent.index(element) + 1, etree.Comment(note))
    else:
        for comment in comments:
            parent.remove(comment)


def _set_message_note(message, note: Any) -> None:
    if not isinstance(note, str):
        raise IncrementalOutputError("IR note must be a string")
    leading_comments = []
    for child in message:
        if child.tag is etree.Comment:
            leading_comments.append(child)
            continue
        break
    if note:
        if leading_comments:
            leading_comments[0].text = note
            for comment in leading_comments[1:]:
                message.remove(comment)
        else:
            message.insert(0, etree.Comment(note))
    else:
        for comment in leading_comments:
            message.remove(comment)


def _remove_field_block(message, field) -> list:
    block = [field, *_following_comments(message, field)]
    for element in block:
        message.remove(element)
    return block


def _insert_field_block(message, index: int, block: list) -> None:
    fields = list(message.findall("field"))
    if index < 0 or index > len(fields):
        raise IncrementalOutputError(
            f"IR field index {index} is outside 0-{len(fields)}"
        )
    child_index = message.index(fields[index]) if index < len(fields) else len(message)
    for offset, element in enumerate(block):
        message.insert(child_index + offset, element)


def _build_message(specification: Any):
    if not isinstance(specification, dict):
        raise IncrementalOutputError("insert_message requires message object")
    attributes = specification.get("attributes")
    fields = specification.get("fields", [])
    if not isinstance(attributes, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in attributes.items()
    ):
        raise IncrementalOutputError(
            "insert_message requires string attributes object"
        )
    if not isinstance(fields, list):
        raise IncrementalOutputError("insert_message fields must be an array")
    message = etree.Element("message", **attributes)
    note = specification.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise IncrementalOutputError("insert_message note must be a string")
        if note:
            message.append(etree.Comment(note))
    for field_spec in fields:
        if not isinstance(field_spec, dict):
            raise IncrementalOutputError("inserted field must be an object")
        field_attributes = field_spec.get("attributes")
        if not isinstance(field_attributes, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in field_attributes.items()
        ):
            raise IncrementalOutputError(
                "inserted field requires string attributes object"
            )
        message.append(etree.Element("field", **field_attributes))
        field_note = field_spec.get("note")
        if field_note is not None:
            if not isinstance(field_note, str):
                raise IncrementalOutputError("inserted field note must be a string")
            if field_note:
                message.append(etree.Comment(field_note))
    return message


def _insert_message(root, index: int, message) -> None:
    if root.tag != "ir":
        raise IncrementalOutputError("message insertion requires an ir root")
    messages = list(root.findall("message"))
    if index < 0 or index > len(messages):
        raise IncrementalOutputError(
            f"IR message index {index} is outside 0-{len(messages)}"
        )
    child_index = root.index(messages[index]) if index < len(messages) else len(root)
    root.insert(child_index, message)


def _validate_proto_ir(root) -> None:
    messages = _messages(root)
    if not messages:
        raise IncrementalOutputError("protoIR contains no messages")
    for message in messages:
        if not message.get("name"):
            raise IncrementalOutputError("protoIR message is missing name")
        for field in message.findall("field"):
            missing = [
                key
                for key in ("name", "type", "length", "value")
                if key not in field.attrib
            ]
            if missing:
                raise IncrementalOutputError(
                    f"protoIR field is missing attributes: {', '.join(missing)}"
                )
            if field.get("type") not in {"constant", "variable"}:
                raise IncrementalOutputError(
                    f"invalid protoIR field type: {field.get('type')!r}"
                )


def apply_ir_delta(source: str, delta: dict[str, Any]) -> str:
    """Apply semantic message/field operations to protoIR XML."""
    if delta.get("base_sha256") != content_sha256(source):
        raise IncrementalOutputError("IR delta base_sha256 mismatch")
    operations = delta.get("ops")
    if not isinstance(operations, list) or not operations:
        raise IncrementalOutputError("IR delta requires a non-empty ops list")
    try:
        parser = etree.XMLParser(remove_blank_text=False, remove_comments=False)
        root = etree.fromstring(source.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as error:
        raise IncrementalOutputError(f"baseline IR is invalid XML: {error}") from error

    for operation in operations:
        if not isinstance(operation, dict):
            raise IncrementalOutputError("each IR operation must be an object")
        kind = operation.get("op")
        if kind == "insert_message":
            index = operation.get("index")
            if not isinstance(index, int) or isinstance(index, bool):
                raise IncrementalOutputError("insert_message requires integer index")
            _insert_message(root, index, _build_message(operation.get("value")))
            continue

        message = _find_message(root, operation.get("message"))
        if kind == "update_message":
            _attribute_changes(message, operation)
        elif kind == "delete_message":
            if root.tag != "ir" or message.getparent() is not root:
                raise IncrementalOutputError(
                    "delete_message requires a direct message under ir"
                )
            root.remove(message)
        elif kind == "move_message":
            index = operation.get("index")
            if not isinstance(index, int) or isinstance(index, bool):
                raise IncrementalOutputError("move_message requires integer index")
            if root.tag != "ir" or message.getparent() is not root:
                raise IncrementalOutputError(
                    "move_message requires a direct message under ir"
                )
            root.remove(message)
            _insert_message(root, index, message)
        elif kind == "set_message_note":
            _set_message_note(message, operation.get("note"))
        elif kind == "update_field":
            field = _find_field(message, operation.get("field"))
            _attribute_changes(field, operation)
        elif kind == "insert_field":
            index = operation.get("index")
            attributes = operation.get("attributes")
            if not isinstance(index, int) or isinstance(index, bool):
                raise IncrementalOutputError("insert_field requires integer index")
            if not isinstance(attributes, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in attributes.items()
            ):
                raise IncrementalOutputError(
                    "insert_field requires string attributes object"
                )
            field = etree.Element("field", **attributes)
            block = [field]
            note = operation.get("note")
            if note is not None:
                if not isinstance(note, str):
                    raise IncrementalOutputError("insert_field note must be a string")
                if note:
                    block.append(etree.Comment(note))
            _insert_field_block(message, index, block)
        elif kind == "delete_field":
            field = _find_field(message, operation.get("field"))
            _remove_field_block(message, field)
        elif kind == "move_field":
            field = _find_field(message, operation.get("field"))
            index = operation.get("index")
            if not isinstance(index, int) or isinstance(index, bool):
                raise IncrementalOutputError("move_field requires integer index")
            block = _remove_field_block(message, field)
            _insert_field_block(message, index, block)
        elif kind == "set_field_note":
            field = _find_field(message, operation.get("field"))
            _set_note(message, field, operation.get("note"))
        else:
            raise IncrementalOutputError(f"unsupported IR operation: {kind!r}")

    _validate_proto_ir(root)
    evolved = etree.tostring(root, encoding="unicode", pretty_print=True)
    if content_sha256(evolved) == content_sha256(source):
        raise IncrementalOutputError("IR delta made no change")
    return evolved
