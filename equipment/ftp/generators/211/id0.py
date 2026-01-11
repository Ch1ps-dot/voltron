def generate_211():
    """Generate one 211 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # ReplyCode: constant "211" (3 bytes)
    reply_code = b'211'

    # Separator: constant 0x20 (space)
    separator = b'\x20'

    # Text: variable, ASCII excluding CR, LF; choose a reasonable length
    # Use letters, digits, space and punctuation (all ASCII) but exclude CR and LF
    allowed_chars = string.ascii_letters + string.digits + ' ' + string.punctuation
    text_length = random.randint(10, 60)
    text_str = ''.join(random.choice(allowed_chars) for _ in range(text_length))
    # Ensure no CR or LF just in case
    text_str = text_str.replace('\r', '').replace('\n', '')
    text = text_str.encode('ascii')

    # EndOfLine: constant 0x0D0A (CR LF)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in order
    message = reply_code + separator + text + end_of_line

    return message