def generate_120():
    """Generate one 120 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode: constant "120" (3 bytes)
    message += b'120'
    
    # Whitespace: constant 0x20 (single space)
    message += b'\x20'
    
    # ReplyText: variable, ASCII printable except CR, LF
    import random
    # Choose a representative human-readable message including an estimated minute value
    minutes = random.randint(1, 59)
    reply_text = f"Service ready in {minutes} minutes"
    # Encode as ASCII (no CR or LF included)
    message += reply_text.encode('ascii')
    
    # EndOfLine: constant 0x0D0A
    message += b'\x0d\x0a'
    
    return message