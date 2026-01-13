def generate_RNTO():
    """Generate one RNTO message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode: constant "RNTO" (4 bytes)
    command = b'RNTO'
    
    # SP: single space (0x20)
    sp = b'\x20'
    
    # Pathname: variable, printable ASCII 0x20-0x7E excluding CR and LF
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F) if c not in (0x0A, 0x0D))
    # choose a reasonable length for the pathname (server-dependent); at least 1 char
    pathname_length = random.randint(1, 64)
    pathname_str = ''.join(random.choice(allowed_chars) for _ in range(pathname_length))
    pathname_bytes = pathname_str.encode('ascii')
    
    # CRLF: constant 0x0D0A
    crlf = b'\x0D\x0A'
    
    # Concatenate fields in the exact order
    message = command + sp + pathname_bytes + crlf
    
    return message