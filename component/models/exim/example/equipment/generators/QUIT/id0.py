def generate() -> bytes:
    # QUIT command: constant verb "QUIT" followed by CRLF
    return b"QUIT\r\n"