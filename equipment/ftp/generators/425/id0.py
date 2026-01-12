def generate_425():
    """Generate one 425 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode: constant "425" (3 bytes)
    message += b'425'
    
    # Whitespace: constant 0x20 (1 byte)
    message += b'\x20'
    
    # ReplyText: constant "Can't open data connection." (ASCII)
    message += b"Can't open data connection."
    
    # EndOfLine: CRLF 0x0D0A (2 bytes)
    message += b'\x0d\x0a'
    
    return message