def generate_226():
    """Generate one 226 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # ReplyCode: constant "226" (3 bytes)
    message += b'226'

    # Whitespace: constant 0x20 (space, 1 byte)
    message += bytes([0x20])

    # ReplyText: variable, ASCII printable excluding CR and LF
    # Choose a reasonable random length and generate ASCII printable characters (space through ~)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    reply_text_length = random.randint(5, 30)  # choose a reasonable length
    reply_text = ''.join(random.choices(allowed_chars, k=reply_text_length))
    # Ensure no CR or LF (they aren't in allowed_chars), encode as ASCII
    message += reply_text.encode('ascii')

    # EndOfLine: constant 0x0D0A (CR LF, 2 bytes)
    message += b'\x0d\x0a'

    return message