def generate_HELP():
    """Generate one HELP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode: constant "HELP" (4 bytes)
    message += b'HELP'
    
    # ArgumentString: generate a random printable NVT-ASCII string (0x20-0x7E), length 1..12
    # Include SpaceIfArgument (0x20) before the argument when present.
    arg_len = random.randint(1, 12)
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F))  # 0x20 .. 0x7E
    argument = ''.join(random.choice(allowed_chars) for _ in range(arg_len))
    # Ensure ASCII encoding is valid (characters are in 0x20-0x7E)
    message += b'\x20' + argument.encode('ascii')
    
    # EndOfLine: constant CRLF (0x0D0A)
    message += b'\x0D\x0A'
    
    return message