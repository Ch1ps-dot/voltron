def input_init():
    """Generate one 120 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant "120", 3 bytes)
    reply_code = b'120'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'

    # Field 3: ReplyText (variable, ASCII printable except CR, LF, length undefined)
    # Use a reasonable representative value: "Service ready in N minutes"
    minutes = random.randint(1, 60)
    reply_text_str = f"Service ready in {minutes} minutes"
    # Ensure only ASCII printable characters excluding CR and LF
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Filter just in case (shouldn't be needed for the constructed string)
    reply_text_str = ''.join(ch for ch in reply_text_str if ch in allowed_chars)
    reply_text = reply_text_str.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in order
    message += reply_code
    message += whitespace
    message += reply_text
    message += end_of_line

    return message