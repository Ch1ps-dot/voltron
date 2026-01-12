def generate_530():
    """Generate one 530 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # ReplyCode: constant "530"
    message += b'530'
    
    # Whitespace: constant 0x20 (space)
    message += b'\x20'
    
    # MessageText: variable, ASCII excluding CR, LF. Choose a representative server message.
    options = [
        'Not logged in.',
        'Please login with USER and PASS.',
        'Authentication failed.',
        'Login incorrect.'
    ]
    text = random.choice(options)
    # Encode as ASCII (no CR or LF in options)
    message += text.encode('ascii')
    
    # EndOfLine: constant 0x0D0A (CRLF)
    message += bytes.fromhex('0D0A')
    
    return message