def generate_SITE():
    """Generate one SITE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    import random

    message = b''

    # CommandCode (constant "SITE")
    message += b'SITE'

    # Whitespace (constant 0x20)
    message += b'\x20'

    # Arguments (variable, NVT-ASCII printable characters excluding CR and LF)
    # Choose a reasonable length between 1 and 64
    length = random.randint(1, 64)
    # Build allowed NVT-ASCII characters (0x20 to 0x7E) excluding CR (0x0D) and LF (0x0A)
    allowed_chars = [chr(c) for c in range(0x20, 0x7F) if c not in (0x0A, 0x0D)]
    args_str = ''.join(random.choices(allowed_chars, k=length))
    message += args_str.encode('ascii')

    # EndOfLine (constant 0x0D0A)
    message += b'\x0D\x0A'

    return message