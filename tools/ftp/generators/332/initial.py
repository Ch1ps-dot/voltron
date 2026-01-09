def input_init():
    """Generate one 332 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # ReplyCode: constant "332" (3 bytes)
    message += b'332'

    # Whitespace: constant 0x20 (1 byte)
    message += b'\x20'

    # ReplyText: variable, ASCII excluding CR, LF, choose a reasonable random message
    # Use visible ASCII (letters, digits, punctuation, space)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    length = random.randint(12, 40)  # reasonable length for a human-readable reply
    reply_text = ''.join(random.choices(allowed_chars, k=length))
    # Ensure it does not end with CR or LF (we excluded them from allowed_chars)
    reply_text_bytes = reply_text.encode('ascii')

    message += reply_text_bytes

    # EndOfLine: constant 0x0D0A (CR LF)
    message += b'\x0D\x0A'
    
    return message