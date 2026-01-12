def generate_215():
    """Generate one 215 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: ReplyCode (constant "215", 3 bytes)
    reply_code = b'215'
    message += reply_code

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'
    message += whitespace

    # Field 3: SystemType (variable, undefined length, ASCII printable characters excluding CR/LF)
    # Choose a reasonable length consistent with protocol conventions
    length = random.randint(8, 20)
    printable_ascii = [chr(c) for c in range(0x20, 0x7f)]  # 0x20 (space) to 0x7E (~)
    system_type_str = ''.join(random.choices(printable_ascii, k=length))
    system_type = system_type_str.encode('ascii')
    message += system_type

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0d\x0a'
    message += end_of_line

    return message