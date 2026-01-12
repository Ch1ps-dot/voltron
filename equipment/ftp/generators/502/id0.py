def generate_502():
    """Generate one 502 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # ReplyCode: constant "502" (3 bytes)
    reply_code = b'502'
    message += reply_code

    # Whitespace: constant 0x20 (space)
    message += b'\x20'

    # ReplyText: variable, ASCII excluding CR and LF, length undefined -> choose a reasonable length
    # Build allowed ASCII characters excluding CR and LF
    allowed_chars = ''.join(ch for ch in string.printable if ch not in '\r\n')
    # Choose a reasonable human-readable length for FTP reply text
    text_length = random.randint(20, 40)
    reply_text_str = ''.join(random.choices(allowed_chars, k=text_length))
    # Encode as ASCII
    reply_text = reply_text_str.encode('ascii')
    message += reply_text

    # EndOfLine: constant CR LF (0x0D0A)
    message += b'\x0D\x0A'
    
    return message