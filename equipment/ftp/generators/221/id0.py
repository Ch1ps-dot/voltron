def generate_221():
    """Generate one 221 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # ReplyCode: constant "221" (3 bytes)
    message += b'221'
    
    # Whitespace: constant 0x20 (1 byte)
    message += b'\x20'
    
    # ReplyText: variable, ASCII excluding CR and LF, optional
    # Decide randomly whether to include a textual response
    include_text = random.choice([True, False])
    if include_text:
        # Choose a reasonable length for the textual response
        length = random.randint(1, 60)
        allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
        # Ensure CR and LF are not present (they are not in the chosen sets, but remove defensively)
        allowed_chars = allowed_chars.replace('\r', '').replace('\n', '')
        reply_text = ''.join(random.choices(allowed_chars, k=length))
        reply_text_bytes = reply_text.encode('ascii')
    else:
        reply_text_bytes = b''
    message += reply_text_bytes

    # EndOfLine: constant 0x0D0A (2 bytes)
    message += b'\x0d\x0a'
    
    return message