def input_init():
    """Generate one 502 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant "502", 3 bytes)
    reply_code = b'502'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = bytes([0x20])

    # Field 3: ReplyText (variable, ASCII excluding CR and LF, length undefined)
    # Choose a reasonable length between 10 and 60 and generate ASCII characters excluding CR/LF
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    text_length = random.randint(10, 60)
    reply_text_str = ''.join(random.choices(allowed_chars, k=text_length))
    reply_text = reply_text_str.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in order
    message = reply_code + whitespace + reply_text + end_of_line

    return message