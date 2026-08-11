#!/usr/bin/env python3
"""Convert VoltronBench AFLNet replay seeds into per-seed JSON assets.

The replay representation is a sequence of little-endian u32 payload lengths
followed by the corresponding bytes.  Payloads are base64 encoded in JSON so
that every protocol byte is retained exactly.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable


TARGETS = {
    "bftpd": ("FTP/BFTPD/in-ftp-replay", "ftp"),
    "exim": ("SMTP/Exim/in-smtp-replay", "smtp"),
    "forked-daapd": ("DAAP/forked-daapd/in-daap-replay", "daap"),
    "kamailio": ("SIP/Kamailio/in-sip-replay", "sip"),
    "lightftp": ("FTP/LightFTP/in-ftp-replay", "ftp"),
    # VoltronBench creates Lighttpd's replay directory at image-build time by
    # wrapping each raw seed as one little-endian length-prefixed message.
    "lighttpd": ("HTTP/Lighttpd1/in-http", "http"),
    "live555": ("RTSP/Live555/in-rtsp-replay", "rtsp"),
    "proftpd": ("FTP/ProFTPD/in-ftp-replay", "ftp"),
    "pureftpd": ("FTP/PureFTPD/in-ftp-replay", "ftp"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_replay(data: bytes) -> list[bytes]:
    """Decode the StateAFL/AFLNet replay stream without accepting truncation."""
    messages: list[bytes] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 4:
            raise ValueError(f"truncated length prefix at byte {offset}")
        length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if length > len(data) - offset:
            raise ValueError(
                f"payload at byte {offset} declares {length} bytes, "
                f"only {len(data) - offset} remain"
            )
        messages.append(data[offset:offset + length])
        offset += length
    if not messages:
        raise ValueError("replay seed contains no messages")
    return messages


def encode_replay(messages: Iterable[bytes]) -> bytes:
    return b"".join(
        struct.pack("<I", len(message)) + message for message in messages
    )


def seed_document(
    *, target: str, protocol: str, source_path: Path, source_root: Path,
    replay_data: bytes, source_kind: str,
) -> dict:
    messages = decode_replay(replay_data)
    relative_source = source_path.relative_to(source_root).as_posix()
    return {
        "format": "voltron-aflnet-seed",
        "version": 1,
        "target": target,
        "protocol": protocol,
        "source": {
            "path": relative_source,
            "sha256": sha256(source_path.read_bytes()),
            "framing": "aflnet-replay-length-prefix",
            "length_encoding": "little-endian-u32",
            "source_kind": source_kind,
        },
        "messages": [
            {
                "index": index,
                "length": len(message),
                "payload_b64": base64.b64encode(message).decode("ascii"),
            }
            for index, message in enumerate(messages)
        ],
        "sequence_sha256": sha256(b"".join(messages)),
        "replay_sha256": sha256(replay_data),
    }


def convert_target(subject_root: Path, bench_root: Path, target: str) -> list[Path]:
    relative_dir, protocol = TARGETS[target]
    input_dir = bench_root / relative_dir
    if not input_dir.is_dir():
        raise FileNotFoundError(f"missing seed directory: {input_dir}")
    output_dir = subject_root / target / "aflnet_seeds"
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    manifest_seeds = []
    for source_path in sorted(path for path in input_dir.iterdir() if path.is_file()):
        source = source_path.read_bytes()
        if target == "lighttpd":
            replay_data = encode_replay([source])
            source_kind = "raw_seed_wrapped_like_voltronbench_stateafl"
        else:
            replay_data = source
            source_kind = "aflnet_replay_seed"
        document = seed_document(
            target=target,
            protocol=protocol,
            source_path=source_path,
            source_root=bench_root,
            replay_data=replay_data,
            source_kind=source_kind,
        )
        output_path = output_dir / f"{source_path.stem}.json"
        output_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        generated.append(output_path)
        manifest_seeds.append({
            "file": output_path.name,
            "source_sha256": document["source"]["sha256"],
            "message_count": len(document["messages"]),
            "sequence_sha256": document["sequence_sha256"],
        })
    manifest = {
        "format": "voltron-aflnet-seed-manifest",
        "version": 1,
        "target": target,
        "protocol": protocol,
        "seed_count": len(manifest_seeds),
        "seeds": manifest_seeds,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return generated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark-root", type=Path,
        default=Path(__file__).resolve().parents[2]
        / "voltronbench" / "benchmark" / "subjects",
    )
    parser.add_argument(
        "--subject-root", type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "subjects",
    )
    parser.add_argument("--target", choices=sorted(TARGETS), action="append")
    args = parser.parse_args()
    targets = args.target or sorted(TARGETS)
    for target in targets:
        generated = convert_target(args.subject_root, args.benchmark_root, target)
        print(f"{target}: converted {len(generated)} seed(s)")


if __name__ == "__main__":
    main()
