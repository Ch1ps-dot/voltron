import base64
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "convert_aflnet_replay_seeds.py"
)
SPEC = importlib.util.spec_from_file_location("aflnet_seed_conversion", MODULE_PATH)
converter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(converter)


def test_replay_round_trip_is_byte_exact():
    messages = [b"EHLO local\r\n", b"\x00binary\xff"]
    replay = converter.encode_replay(messages)
    assert converter.decode_replay(replay) == messages


def test_replay_rejects_truncated_payload():
    with pytest.raises(ValueError, match="declares"):
        converter.decode_replay(b"\x05\x00\x00\x00abc")


def test_seed_document_preserves_payload_and_metadata(tmp_path):
    source_root = tmp_path / "bench"
    source_dir = source_root / "SMTP" / "Exim" / "in-smtp-replay"
    source_dir.mkdir(parents=True)
    source = source_dir / "seed.raw"
    replay = converter.encode_replay([b"EHLO local\r\n", b"QUIT\r\n"])
    source.write_bytes(replay)

    document = converter.seed_document(
        target="exim", protocol="smtp", source_path=source,
        source_root=source_root, replay_data=replay,
        source_kind="aflnet_replay_seed",
    )

    decoded = [base64.b64decode(item["payload_b64"]) for item in document["messages"]]
    assert decoded == [b"EHLO local\r\n", b"QUIT\r\n"]
    assert document["source"]["path"] == "SMTP/Exim/in-smtp-replay/seed.raw"
