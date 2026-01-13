def generate_HELP():
    """Generate one HELP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode: constant "HELP" (4 ASCII bytes)
    message += b'HELP'
    
    # Decide to include an argument (the SpaceIfArgument constant must be present if an argument is supplied)
    include_argument = True

    if include_argument:
        # SpaceIfArgument: constant 0x20
        message += b'\x20'
        # ArgumentString: NVT-ASCII printable characters (0x20-0x7E), excluding CR and LF
        allowed_chars = [chr(c) for c in range(0x20, 0x7F) if c not in (0x0D, 0x0A)]
        arg_len = random.randint(1, 12)  # choose a reasonable length
        argument = ''.join(random.choices(allowed_chars, k=arg_len))
        message += argument.encode('ascii')
    
    # EndOfLine: constant CRLF 0x0D0A
    message += b'\x0D\x0A'
    
    return message