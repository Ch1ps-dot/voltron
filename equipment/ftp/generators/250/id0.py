def generate_250():
    """Generate one 250 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode: constant "250" (3 bytes)
    message += b'250'
    
    # Whitespace: constant 0x20 (space)
    message += b'\x20'
    
    # ReplyText: variable, ASCII excluding CR and LF, undefined length -> choose a reasonable length
    import random
    import string
    # Allowed ASCII characters excluding CR and LF
    allowed_chars = ''.join(ch for ch in (string.ascii_letters + string.digits + string.punctuation + ' ') if ch not in '\r\n')
    text_length = random.randint(20, 60)
    reply_text = ''.join(random.choices(allowed_chars, k=text_length))
    # Ensure ASCII encoding
    message += reply_text.encode('ascii')
    
    # EndOfLine: constant 0x0D0A (CRLF)
    message += b'\x0d\x0a'
    
    return message