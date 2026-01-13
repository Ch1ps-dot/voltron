def generate_RNFR():
    """Generate one RNFR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # CommandCode: constant "RNFR" (4 bytes ASCII)
    message += b'RNFR'

    # Whitespace: single SP (0x20)
    message += bytes([0x20])

    # Pathname: variable length, ASCII excluding CR and LF, may include SP
    # Choose a reasonable length and ensure at least one non-space character
    min_len = 1
    max_len = 64
    pathname_len = random.randint(min_len, max_len)

    non_space_chars = string.ascii_letters + string.digits + "._-/"  # allowed non-space characters
    allowed_chars = non_space_chars + " "  # spaces allowed

    if pathname_len == 1:
        pathname = random.choice(non_space_chars)
    else:
        # ensure first char is non-space to avoid an all-space pathname
        first_char = random.choice(non_space_chars)
        rest = ''.join(random.choice(allowed_chars) for _ in range(pathname_len - 1))
        pathname = first_char + rest

    pathname_bytes = pathname.encode('ascii')
    message += pathname_bytes

    # EndOfLine: CRLF (0x0D0A)
    message += b'\x0d\x0a'

    return message