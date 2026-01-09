def input_init():
    """Generate one 425 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field: ReplyCode (constant, 3B) -> "425"
    message += b'425'
    
    # Field: Whitespace (constant, 1B) -> 0x20 (space)
    message += b'\x20'
    
    # Field: ReplyText (constant, 28B) -> "Can't open data connection."
    message += b"Can't open data connection."
    
    # Field: EndOfLine (constant, 2B) -> 0x0D0A (CRLF)
    message += b'\x0D\x0A'
    
    return message