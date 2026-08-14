def generate() -> bytes:
    # SMTP QUIT request: verb "QUIT" followed by line-ending "\r\n"
    # Constants per IR field table: verb is ASCII "QUIT", line-ending is CRLF
    verb = b"QUIT"
    line_ending = b"\r\n"
    return verb + line_ending