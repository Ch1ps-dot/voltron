def packet_parser(response: bytes) -> bytes:
    """
    Extract the SMTP reply code from a server response.
    Returns the three-digit numeric code as UTF-8 bytes,
    or b"" if not found.
    """
    if not isinstance(response, bytes):
        return b""
    try:
        text = response.decode("utf-8", errors="replace")
    except Exception:
        return b""
    # First non-empty line (SMTP reply line)
    for line in text.splitlines():
        line = line.strip()
        # SMTP reply code: three digits at start of line
        if len(line) >= 3 and line[:3].isdigit():
            code = line[:3]
            # Validate against known codes (optional but keeps contract)
            # We'll just return the code as found
            return code.encode("utf-8")
    return b""