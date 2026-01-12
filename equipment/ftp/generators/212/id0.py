def generate_212():
    """Generate one 212 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # ReplyCode (constant "212", 3 bytes)
    message += b'212'

    # Whitespace (constant 0x20, 1 byte)
    message += b'\x20'

    # Text (variable, ASCII excluding CR and LF, length undefined -> choose reasonable length)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    text_length = random.randint(10, 40)
    text_value = ''.join(random.choices(allowed_chars, k=text_length))
    message += text_value.encode('ascii')

    # EndOfLine (constant 0x0D0A, 2 bytes)
    message += b'\x0d\x0a'

    return message