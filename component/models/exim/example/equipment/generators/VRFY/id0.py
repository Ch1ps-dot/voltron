def generate() -> bytes:
    verb = b"VRFY"
    sp = b" "
    # VRFY argument: a valid user name, e.g., "user"
    argument = b"user"
    crlf = b"\r\n"
    return verb + sp + argument + crlf