def generate_215():
    """Generate one 215 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # ReplyCode: constant "215" (3 bytes)
    reply_code = b'215'
    message += reply_code

    # Whitespace: constant 0x20 (space)
    message += b'\x20'

    # SystemType: variable, ASCII printable characters (0x20-0x7E), excluding CR/LF
    # Choose a reasonable undefined length between 7 and 20 characters
    printable_chars = ''.join(chr(i) for i in range(0x20, 0x7F))
    sys_len = random.randint(7, 20)
    system_type_str = ''.join(random.choice(printable_chars) for _ in range(sys_len))
    system_type_bytes = system_type_str.encode('ascii')
    message += system_type_bytes

    # EndOfLine: constant 0x0D0A (CR LF)
    message += b'\x0d\x0a'

    return message