def generate_213():
    """Generate one 213 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: ReplyCode (constant "213")
    message += b'213'

    # Field 2: Whitespace (constant 0x20)
    message += b'\x20'

    # Field 3: FileSize (variable, ASCII digits). Choose a reasonable non-negative size.
    file_size = random.randint(0, 10**9)  # up to 10 digits
    message += str(file_size).encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A)
    message += b'\x0d\x0a'

    return message