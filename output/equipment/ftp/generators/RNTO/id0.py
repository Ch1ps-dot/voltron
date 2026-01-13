def generate_RNTO():
    """Generate one RNTO message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # Field 1: CommandCode (constant "RNTO", 4 bytes)
    command_code = b'RNTO'
    
    # Field 2: SP (constant single space 0x20)
    sp = b'\x20'
    
    # Field 3: Pathname (variable, printable ASCII 0x20-0x7E excluding CR/LF)
    # Choose a reasonable length (1..32) and generate a random pathname.
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F) if c not in (0x0D, 0x0A))
    pathname_length = random.randint(1, 32)
    pathname_str = ''.join(random.choice(allowed_chars) for _ in range(pathname_length))
    pathname = pathname_str.encode('ascii')
    
    # Field 4: CRLF (constant 0x0D0A)
    crlf = b'\x0D\x0A'
    
    # Concatenate fields in order
    message = command_code + sp + pathname + crlf
    
    return message