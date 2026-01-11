def generate_250():
    """Generate one 250 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random, string

    message = b''
    
    # ReplyCode: constant "250" (3 ASCII digits)
    message += b'250'

    # Whitespace: constant 0x20 (space)
    message += b'\x20'

    # ReplyText: variable, ASCII excluding CR and LF, length chosen reasonably
    allowed_chars = ''.join(ch for ch in (string.ascii_letters + string.digits + string.punctuation + ' ') if ch not in '\r\n')
    # Choose a reasonable length for a human-readable reply text
    text_length = random.randint(20, 60)
    reply_text = ''.join(random.choice(allowed_chars) for _ in range(text_length))
    message += reply_text.encode('ascii')

    # EndOfLine: constant CR LF (0x0D0A)
    message += b'\x0D\x0A'
    
    return message