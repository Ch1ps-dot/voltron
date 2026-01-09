def input_init():
    """Generate one 213 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: ReplyCode (constant, 3B, value "213")
    reply_code = b'213'

    # Field 2: Whitespace (constant, 1B, value 0x20)
    whitespace = b'\x20'

    # Field 3: FileSize (variable, undefined length, ASCII digits 0-9)
    # Choose a reasonable file size (0 to 1 billion bytes) and encode as ASCII digits
    file_size_int = random.randint(0, 10**9)
    file_size = str(file_size_int).encode('ascii')

    # Field 4: EndOfLine (constant, 2B, value 0x0D0A)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in the exact order specified by the protoIR
    message = reply_code + whitespace + file_size + end_of_line

    return message