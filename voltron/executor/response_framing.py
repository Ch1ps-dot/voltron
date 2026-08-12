"""Protocol-aware response framing for one TCP receive batch.

The receive batch is retained verbatim for diagnostics.  These splitters only
separate boundaries that are explicit in the relevant wire protocol; they
never split arbitrary TCP input on CRLF.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ResponseFrame:
    data: bytes
    offset_start: int
    offset_end: int


_STATUS_LINE = re.compile(br'^(\d{3})([ -])', re.MULTILINE)


def _line_protocol_frames(data: bytes) -> list[ResponseFrame]:
    """Split FTP/SMTP replies, preserving xyz- ... xyz multiline replies."""
    frames: list[ResponseFrame] = []
    cursor = 0
    while cursor < len(data):
        match = _STATUS_LINE.search(data, cursor)
        if match is None:
            break
        if match.start() > cursor:
            # A partial/non-status prefix has no safe standalone boundary.
            break
        code, delimiter = match.group(1), match.group(2)
        line_end = data.find(b'\n', match.end())
        if line_end < 0:
            break
        end = line_end + 1
        if delimiter == b'-':
            terminator = re.compile(br'(?m)^' + re.escape(code) + br' ')
            terminal = terminator.search(data, end)
            if terminal is None:
                break
            final_end = data.find(b'\n', terminal.end())
            if final_end < 0:
                break
            end = final_end + 1
        frames.append(ResponseFrame(data[cursor:end], cursor, end))
        cursor = end
    if cursor < len(data) or not frames:
        return [ResponseFrame(data, 0, len(data))]
    return frames


def _content_length_frames(data: bytes) -> list[ResponseFrame]:
    frames: list[ResponseFrame] = []
    cursor = 0
    while cursor < len(data):
        header_end = data.find(b'\r\n\r\n', cursor)
        separator_size = 4
        if header_end < 0:
            header_end = data.find(b'\n\n', cursor)
            separator_size = 2
        if header_end < 0:
            break
        headers = data[cursor:header_end]
        length_match = re.search(br'(?im)^content-length\s*:\s*(\d+)\s*$', headers)
        if length_match is None:
            # Header-only status responses are complete; do not guess a body.
            end = header_end + separator_size
        else:
            end = header_end + separator_size + int(length_match.group(1))
            if end > len(data):
                break
        frames.append(ResponseFrame(data[cursor:end], cursor, end))
        cursor = end
    if cursor < len(data) or not frames:
        return [ResponseFrame(data, 0, len(data))]
    return frames


def _daap_frames(data: bytes) -> list[ResponseFrame]:
    """DAAP atom framing: 4-byte tag followed by a big-endian length."""
    frames: list[ResponseFrame] = []
    cursor = 0
    while cursor + 8 <= len(data):
        length = int.from_bytes(data[cursor + 4:cursor + 8], 'big')
        end = cursor + 8 + length
        if end > len(data):
            break
        frames.append(ResponseFrame(data[cursor:end], cursor, end))
        cursor = end
    if cursor < len(data) or not frames:
        return [ResponseFrame(data, 0, len(data))]
    return frames


def split_response_frames(protocol: str, data: bytes) -> list[ResponseFrame]:
    protocol = (protocol or '').lower()
    if protocol in {'ftp', 'smtp'}:
        return _line_protocol_frames(data)
    if protocol in {'http', 'sip', 'rtsp'}:
        return _content_length_frames(data)
    if protocol == 'daap':
        return _daap_frames(data)
    return [ResponseFrame(data, 0, len(data))]
