"""Safe filesystem paths for protocol component type names."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


_SAFE_BYTES = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
)
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
DEFAULT_MAX_SLUG_LENGTH = 180


def type_to_slug(
    type_name: str,
    *,
    max_length: int = DEFAULT_MAX_SLUG_LENGTH,
) -> str:
    """Return a stable, collision-resistant filename for a display type.

    Safe ASCII characters remain readable. Every other UTF-8 byte is encoded
    as ``%HH``; ``%`` itself is encoded, so names such as ``/update`` and
    ``%2Fupdate`` cannot collide. Long names receive a digest suffix.
    """
    if not isinstance(type_name, str):
        raise TypeError("component type name must be a string")
    if "\x00" in type_name:
        raise ValueError("component type name must not contain NUL")
    if max_length < 32:
        raise ValueError("max_length must be at least 32")

    raw = type_name.encode("utf-8")
    tokens = [
        chr(byte) if byte in _SAFE_BYTES else f"%{byte:02X}"
        for byte in raw
    ]
    if not tokens:
        tokens = ["%00"]

    # Avoid dot entries, hidden names, and Windows device names even though
    # the benchmark normally runs on Linux.
    if tokens[0] == ".":
        tokens[0] = "%2E"
    slug = "".join(tokens)
    stem = slug.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        first = slug[0].encode("ascii")[0]
        slug = f"%{first:02X}{slug[1:]}"

    if len(slug) > max_length:
        suffix = f"~{hashlib.sha256(raw).hexdigest()[:16]}"
        prefix_limit = max_length - len(suffix)
        prefix: list[str] = []
        prefix_length = 0
        for token in tokens:
            if prefix_length + len(token) > prefix_limit:
                break
            prefix.append(token)
            prefix_length += len(token)
        slug = "".join(prefix) + suffix

    if slug in {"", ".", ".."}:
        raise ValueError("component type produced an unsafe empty path")
    if any(separator and separator in slug for separator in (os.sep, os.altsep)):
        raise ValueError("component type slug contains a path separator")
    return slug


def path_within(root: Path, candidate: Path) -> bool:
    """Return whether *candidate* resolves within *root*."""
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def component_type_dir(root: Path, type_name: str) -> Path:
    """Resolve a type directory and enforce that it stays below *root*."""
    path = root / type_to_slug(type_name)
    if not path_within(root, path):
        raise ValueError(
            f"component type path escapes its root: {type_name!r}"
        )
    return path
