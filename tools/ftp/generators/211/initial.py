def input_init():
    """Generate one 211 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant "211", 3 bytes)
    reply_code = b'211'

    # Field 2: Separator (constant 0x20, space)
    separator = b'\x20'

    # Field 3: Text (variable, ASCII excluding CR, LF, undefined length)
    # Choose a reasonable length for the reply text
    text_length = random.randint(10, 60)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure CR and LF are not present (they are not in allowed_chars)
    text = ''.join(random.choice(allowed_chars) for _ in range(text_length))
    text_bytes = text.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, CRLF)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message = reply_code + separator + text_bytes + end_of_line

    return message