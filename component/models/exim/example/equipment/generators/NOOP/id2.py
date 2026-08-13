def generate() -> bytes:
    # SMTP NOOP command: constant verb, optional parameter, CRLF terminator.
    # Use a non-empty parameter to explore unobserved transitions.
    return b"NOOP TEST\r\n"
