def generate() -> bytes:
    # SEND command: constant verb "SEND", space, FROM: keyword, reverse-path, CRLF
    # All fields are mandatory; reverse-path is variable length (max 256 octets)
    # Use a valid reverse-path: <user@example.com> (22 bytes, including angle brackets)
    # The path must be enclosed in angle brackets; empty path <> is also valid per RFC so we vary
    # Vary the reverse-path to explore different responses (e.g., 500, 554, POLLERR)
    import random
    command = b"SEND"
    space = b" "
    from_keyword = b"FROM:"
    # Choose from a variety of reverse-paths to reach different legal protocol states
    paths = [
        b"<user@example.com>",  # 22 bytes, typical
        b"<>",                  # empty path
        b"<a@b>",               # short path
        b"<user@[127.0.0.1]>",  # address literal
        b"<User@example.com>",  # mixed case local-part
        b"<" + b"a" * 64 + b"@" + b"b" * 63 + b"." + b"c" * 63 + b"." + b"d" * 61 + b">"  # max length path
    ]
    reverse_path = random.choice(paths)
    crlf = b"\r\n"
    return command + space + from_keyword + reverse_path + crlf