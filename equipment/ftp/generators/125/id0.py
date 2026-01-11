def generate_125():
    """Generate one 125 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # ReplyCode: constant "125" (3 bytes)
    message += b'125'
    
    # Whitespace: constant 0x20 (space)
    message += b' '
    
    # ReplyText: variable, ASCII excluding CR and LF
    # Choose a representative valid reply text (RFC959) or a close variant
    candidates = [
        "Data connection already open; transfer starting",
        "Opening data connection; transfer starting",
        "Transfer starting; data connection already open"
    ]
    reply_text = random.choice(candidates)
    # Ensure no CR/LF characters
    reply_text = reply_text.replace('\r', '').replace('\n', '')
    # Encode as ASCII
    message += reply_text.encode('ascii')
    
    # EndOfLine: constant 0x0D0A (CRLF)
    message += b'\r\n'
    
    return message