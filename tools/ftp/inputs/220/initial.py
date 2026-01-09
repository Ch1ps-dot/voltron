def input_init():
    """Generate one 220 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # ReplyCode: constant "220" (3 bytes)
    reply_code = b'220'

    # Whitespace: constant 0x20 (space)
    whitespace = b'\x20'

    # ReplyText: variable, ASCII printable and space (without CR, LF)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # choose a reasonable length for a greeting text
    reply_text_length = random.randint(10, 50)
    reply_text_str = ''.join(random.choices(allowed_chars, k=reply_text_length))
    reply_text = reply_text_str.encode('ascii')

    # EndOfLine: constant 0x0D0A (CR LF)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in order
    message = reply_code + whitespace + reply_text + end_of_line

    return message