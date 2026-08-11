"""Validated, opt-in loading for imported AFLNet replay seeds.

The importer preserves raw network messages.  This module deliberately does
not map them onto generated request types: callers replay the bytes as a
separate pre-fuzzing corpus, after model learning has completed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path


class AFLNetSeedError(ValueError):
    """An imported seed asset is malformed or does not match its manifest."""


@dataclass(frozen=True)
class AFLNetSeed:
    """One raw replay sequence, retained independently of mapper symbols."""

    name: str
    messages: tuple[bytes, ...]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replay_bytes(messages: tuple[bytes, ...]) -> bytes:
    return b"".join(
        struct.pack("<I", len(message)) + message for message in messages
    )


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AFLNetSeedError(f"cannot read {path}: {error}") from error
    if not isinstance(document, dict):
        raise AFLNetSeedError(f"{path}: expected a JSON object")
    return document


def load_aflnet_seeds(subject_root: Path, target: str, protocol: str) -> tuple[AFLNetSeed, ...]:
    """Load one target's converted seeds and verify all stored checksums."""
    seed_dir = subject_root / target / "aflnet_seeds"
    manifest_path = seed_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    if manifest.get("format") != "voltron-aflnet-seed-manifest":
        raise AFLNetSeedError(f"{manifest_path}: unsupported manifest format")
    if manifest.get("version") != 1:
        raise AFLNetSeedError(f"{manifest_path}: unsupported manifest version")
    if manifest.get("target") != target or manifest.get("protocol") != protocol:
        raise AFLNetSeedError(f"{manifest_path}: target or protocol mismatch")
    entries = manifest.get("seeds")
    if not isinstance(entries, list) or manifest.get("seed_count") != len(entries):
        raise AFLNetSeedError(f"{manifest_path}: invalid seed count")

    seeds: list[AFLNetSeed] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise AFLNetSeedError(f"{manifest_path}: invalid seed entry")
        name = entry["file"]
        path = seed_dir / name
        if Path(name).name != name or path.suffix != ".json":
            raise AFLNetSeedError(f"{manifest_path}: unsafe seed filename {name!r}")
        document = _load_json(path)
        if (
            document.get("format") != "voltron-aflnet-seed"
            or document.get("version") != 1
            or document.get("target") != target
            or document.get("protocol") != protocol
        ):
            raise AFLNetSeedError(f"{path}: incompatible seed metadata")
        raw_messages = document.get("messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            raise AFLNetSeedError(f"{path}: seed has no messages")
        messages: list[bytes] = []
        for index, item in enumerate(raw_messages):
            if not isinstance(item, dict) or item.get("index") != index:
                raise AFLNetSeedError(f"{path}: invalid message index {index}")
            try:
                message = base64.b64decode(item["payload_b64"], validate=True)
            except (KeyError, TypeError, ValueError) as error:
                raise AFLNetSeedError(f"{path}: invalid base64 message {index}") from error
            if item.get("length") != len(message):
                raise AFLNetSeedError(f"{path}: message length mismatch at {index}")
            messages.append(message)
        sequence = tuple(messages)
        sequence_hash = _sha256(b"".join(sequence))
        if document.get("sequence_sha256") != sequence_hash:
            raise AFLNetSeedError(f"{path}: sequence checksum mismatch")
        if document.get("replay_sha256") != _sha256(_replay_bytes(sequence)):
            raise AFLNetSeedError(f"{path}: replay checksum mismatch")
        if entry.get("message_count") != len(sequence) or entry.get("sequence_sha256") != sequence_hash:
            raise AFLNetSeedError(f"{manifest_path}: metadata mismatch for {name}")
        seeds.append(AFLNetSeed(name=path.stem, messages=sequence))
    return tuple(seeds)
