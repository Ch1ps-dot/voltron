def generate() -> bytes:
    # Build ETRN SMTP request per RFC 1985
    result = b"ETRN"  # command-verb, constant 4B
    result += b" "    # space, constant 1B
    # optional option-character: we choose to omit it (most common case)
    # node-name: choose a valid domain name for state exploration
    result += b"example.com"  # variable-length node name
    result += b"\r\n"         # line-ending, constant 2B
    return result