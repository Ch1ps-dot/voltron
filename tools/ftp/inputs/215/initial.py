def input_init():
    """Generate one 215 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant, 3 bytes) -> "215"
    reply_code = b'215'

    # Field 2: Whitespace (constant, 1 byte) -> 0x20 (space)
    whitespace = b'\x20'

    # Field 3: SystemType (variable, undefined length, ASCII printable excluding CR/LF)
    # Choose a reasonable random length and create a printable ASCII string (0x20 to 0x7E)
    printable_chars = ''.join(chr(c) for c in range(0x20, 0x7F) if c not in (0x0A, 0x0D))
    # Pick a typical length for a system type description
    syslen = random.randint(6, 24)
    system_type_str = ''.join(random.choices(printable_chars, k=syslen))
    system_type = system_type_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2 bytes) -> 0x0D0A (CR LF)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in order
    message += reply_code
    message += whitespace
    message += system_type
    message += end_of_line

    return message