def generate_SITE():
    """Generate one SITE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # CommandCode: constant "SITE" (4 bytes ASCII)
    message += b'SITE'

    # Whitespace: single SP (0x20)
    message += b'\x20'

    # Arguments: variable, NVT-ASCII characters excluding CR (0x0D) and LF (0x0A)
    # Choose a reasonable random length for the argument (1..60)
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F) if c not in (0x0A, 0x0D))
    arg_length = random.randint(1, 60)
    args = ''.join(random.choice(allowed_chars) for _ in range(arg_length))
    message += args.encode('ascii')

    # EndOfLine: CR LF (0x0D0A)
    message += b'\x0D\x0A'

    return message