def generate_RETR():
    """Generate one RETR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode: constant "RETR" (4 bytes)
    command = b'RETR'
    message += command

    # Whitespace: one or more SP (0x20). Choose between 1 and 4 spaces.
    sp_count = random.randint(1, 4)
    whitespace = b' ' * sp_count
    message += whitespace

    # Pathname: printable NVT-ASCII characters (0x20-0x7E), excluding CR and LF.
    # Must be non-empty; ensure first character is not a space to avoid all-space pathname.
    min_len = 1
    max_len = 32
    name_len = random.randint(min_len, max_len)

    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F))       # 0x20..0x7E
    allowed_first = ''.join(chr(c) for c in range(0x21, 0x7F))       # 0x21..0x7E (not space)

    if name_len == 1:
        pathname = random.choice(allowed_first)
    else:
        first_char = random.choice(allowed_first)
        rest = ''.join(random.choice(allowed_chars) for _ in range(name_len - 1))
        pathname = first_char + rest

    pathname_bytes = pathname.encode('ascii')
    message += pathname_bytes

    # EndOfLine: constant CRLF (0x0D0A)
    message += b'\x0D\x0A'
    
    return message