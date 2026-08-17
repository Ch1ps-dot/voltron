"""Deterministic, protocol-level plausibility checks for response frames.

These checks deliberately validate only the minimum wire shape.  They never
consult an IR response-code catalog, because an unknown but syntactically valid
response must remain eligible for parser repair and model learning.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ResponsePlausibility:
    status: str
    reason: str


_LINE_REPLY = re.compile(br'^(\d{3})([ -])[^\r\n]*\r?\n')
_HTTP_STATUS = re.compile(br'^HTTP/\d+\.\d+\s+\d{3}(?:\s|\r|\n|$)')
_SIP_STATUS = re.compile(br'^SIP/2\.0\s+\d{3}(?:\s|\r|\n|$)')
_RTSP_STATUS = re.compile(br'^RTSP/\d+\.\d+\s+\d{3}(?:\s|\r|\n|$)')
_DAAP_TAG = re.compile(br'^[A-Za-z0-9]{4}$')


def _line_reply_plausibility(response: bytes) -> ResponsePlausibility:
    match = _LINE_REPLY.match(response)
    if match is None:
        return ResponsePlausibility('invalid', 'invalid_status_line')
    if not response.endswith(b'\n'):
        return ResponsePlausibility('invalid', 'unterminated_status_line')
    code, delimiter = match.group(1), match.group(2)
    if delimiter == b'-':
        terminal = re.compile(br'(?m)^' + re.escape(code) + br' [^\r\n]*\r?\n$')
        if terminal.search(response) is None:
            return ResponsePlausibility('invalid', 'unterminated_multiline_reply')
    return ResponsePlausibility('valid', 'status_line')


def _text_status_plausibility(
        response: bytes,
        expression: re.Pattern[bytes],
        protocol: str,
) -> ResponsePlausibility:
    if not expression.match(response):
        return ResponsePlausibility('invalid', f'invalid_{protocol}_status_line')
    if b'\r\n\r\n' not in response and b'\n\n' not in response:
        return ResponsePlausibility('invalid', 'missing_header_terminator')
    return ResponsePlausibility('valid', 'status_line')


def _daap_plausibility(response: bytes) -> ResponsePlausibility:
    if len(response) < 8:
        return ResponsePlausibility('invalid', 'truncated_daap_header')
    if _DAAP_TAG.match(response[:4]) is None:
        return ResponsePlausibility('invalid', 'invalid_daap_tag')
    declared_length = int.from_bytes(response[4:8], 'big')
    if declared_length != len(response) - 8:
        return ResponsePlausibility('invalid', 'daap_length_mismatch')
    return ResponsePlausibility('valid', 'daap_atom')


def classify_response_plausibility(
        protocol: str,
        response: bytes,
) -> ResponsePlausibility:
    """Classify a complete frame without executing generated code or an LLM."""
    if not response:
        return ResponsePlausibility('invalid', 'empty_response')
    protocol = (protocol or '').lower()
    if protocol in {'ftp', 'smtp'}:
        return _line_reply_plausibility(response)
    if protocol == 'http':
        return _text_status_plausibility(response, _HTTP_STATUS, protocol)
    if protocol == 'sip':
        return _text_status_plausibility(response, _SIP_STATUS, protocol)
    if protocol == 'rtsp':
        return _text_status_plausibility(response, _RTSP_STATUS, protocol)
    if protocol == 'daap':
        return _daap_plausibility(response)
    # There is no safe generic validator for arbitrary binary protocols.
    return ResponsePlausibility('unknown', 'no_protocol_validator')
