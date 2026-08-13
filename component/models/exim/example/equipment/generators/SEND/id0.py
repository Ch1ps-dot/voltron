def generate() -> bytes:
    # SEND command: constant verb "SEND", space, FROM: keyword, reverse-path, CRLF
    # All fields are mandatory; reverse-path is variable length (max 256 octets)
    # Use a valid reverse-path: <user@example.com> (22 bytes, including angle brackets)
    # The path must be enclosed in angle brackets; empty path <> is also valid per RFC but we vary
    command = b"SEND"
    space = b" "
    from_keyword = b"FROM:"
    reverse_path = b"<user@example.com>"  # 22 bytes, within 256 limit
    crlf = b"\r\n"
    return command + space + from_keyword + reverse_path + crlf