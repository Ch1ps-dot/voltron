def generate_213():
    """Generate one 213 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # ReplyCode: constant "213"
    message += b'213'
    
    # Whitespace: constant 0x20 (space)
    message += b'\x20'
    
    # FileSize: variable, ASCII digits (0-9), length undefined
    # Choose a reasonable file size between 0 and 10^10-1 and encode as ASCII decimal
    filesize_int = random.randint(0, 10**10 - 1)
    filesize_bytes = str(filesize_int).encode('ascii')
    message += filesize_bytes
    
    # EndOfLine: constant 0x0D0A (CRLF)
    message += b'\x0D\x0A'
    
    return message