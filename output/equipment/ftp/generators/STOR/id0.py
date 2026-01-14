def generate_STOR():
    """Generate one STOR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    import random

    # Constant fields from IR
    command_code = b"STOR"       # 4B ASCII literal
    whitespace = b"\x20"         # single SP

    # Variable Pathname: printable ASCII 0x20-0x7E excluding CR/LF, may include spaces
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F)).replace('\r', '').replace('\n', '')
    # choose a reasonable length for an undefined-length field (1-48 bytes)
    pathname_length = random.randint(1, 48)
    pathname_str = ''.join(random.choice(allowed_chars) for _ in range(pathname_length))
    pathname = pathname_str.encode('ascii')

    # EndOfLine constant CRLF
    end_of_line = b"\x0d\x0a"

    message = command_code + whitespace + pathname + end_of_line
    return message