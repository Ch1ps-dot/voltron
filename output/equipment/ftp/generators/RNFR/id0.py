def generate_RNFR():
    """Generate one RNFR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # Field: CommandCode (constant "RNFR", 4 bytes)
    command = b'RNFR'
    
    # Field: Whitespace (constant SP, 1 byte)
    whitespace = b' '
    
    # Field: Pathname (variable, ASCII excluding CR and LF, may include SP)
    # Choose a reasonable length (1..32) and generate from allowed characters.
    length = random.randint(1, 32)
    allowed = string.ascii_letters + string.digits + "._-/ "  # excludes CR and LF
    pathname_str = ''.join(random.choice(allowed) for _ in range(length))
    pathname = pathname_str.encode('ascii')
    
    # Field: EndOfLine (constant CRLF, 2 bytes)
    eol = bytes([0x0D, 0x0A])
    
    # Concatenate fields in exact order
    message = command + whitespace + pathname + eol
    
    return message