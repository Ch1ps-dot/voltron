def input_init():
    """Generate one 212 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # Field 1: ReplyCode (constant, 3B, value "212")
    reply_code = b'212'

    # Field 2: Whitespace (constant, 1B, value 0x20)
    whitespace = b'\x20'

    # Field 3: Text (variable, undefined length, ASCII excluding CR, LF)
    # Choose a reasonable length and generate ASCII characters excluding CR (0x0D) and LF (0x0A).
    length = random.randint(10, 60)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure no CR or LF are present (they are not in allowed_chars)
    text_str = ''.join(random.choices(allowed_chars, k=length))
    text = text_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2B, value 0x0D0A)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in order
    message = reply_code + whitespace + text + end_of_line

    return message