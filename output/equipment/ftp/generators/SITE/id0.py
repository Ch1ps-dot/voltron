def generate_SITE():
    """Generate one SITE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode: constant "SITE" (4 bytes ASCII)
    message += b'SITE'
    
    # Whitespace: single SP (0x20)
    message += b'\x20'
    
    # Arguments: variable, NVT-ASCII printable characters (0x20-0x7E), excluding CR and LF
    # Choose a reasonable length for the argument (1 to 64 characters)
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F))  # 0x20..0x7E
    arg_len = random.randint(1, 64)
    arguments = ''.join(random.choice(allowed_chars) for _ in range(arg_len))
    message += arguments.encode('ascii')
    
    # EndOfLine: CR LF (0x0D0A)
    message += b'\x0D\x0A'
    
    return message