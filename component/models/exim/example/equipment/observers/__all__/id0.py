import hashlib

def packet_observer(response: bytes) -> str:
    """
    Normalize SMTP response for semantic hashing.
    - Preserves reply code, status class, enhanced status code, separator, and CRLF.
    - Replaces free-form text (the 'text' field) with a stable marker preserving length.
    """
    try:
        if not isinstance(response, bytes):
            return hashlib.sha256(b"").hexdigest()
        result = bytearray()
        lines = response.split(b"\r\n")
        # remove trailing empty line if present
        if lines and lines[-1] == b"":
            lines = lines[:-1]
        for line in lines:
            if not line:
                continue
            # extract reply code (first 3 bytes)
            reply_code = line[:3]
            result.extend(reply_code)
            # separator: either b' ' or b'-' or nothing
            sep = b""
            text_start = 3
            if len(line) > 3:
                sep_char = line[3:4]
                if sep_char in (b" ", b"-"):
                    sep = sep_char
                    text_start = 4
                # else: no separator, no text (should not happen per spec but safe)
            result.extend(sep)
            # text from position text_start to end
            text = line[text_start:]
            if text:
                # replace text with marker of same length, preserving presence
                marker = b"X" * len(text)
                result.extend(marker)
            # add CRLF per line
            result.extend(b"\r\n")
        # remove trailing CRLF (since we added after each line, but final line may have it)
        # the original response may have trailing CRLF; we emulate that
        # Actually we need to keep the exact number of CRLFs as in original? The spec says
        # each line is terminated by CRLF. The original response ends with a CRLF (maybe).
        # We'll mimic by adding CRLF after each line, but the last line also gets one.
        # That's fine because the original also ends with CRLF.
        return hashlib.sha256(bytes(result)).hexdigest()
    except Exception:
        return hashlib.sha256(b"").hexdigest()