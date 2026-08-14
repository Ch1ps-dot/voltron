def generate() -> bytes:
    # SMTP DATA command: verb "DATA" followed by CRLF
    return b"DATA\r\n"