def input_init():
    """Generate one 452 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: ReplyCode (constant, 3B) -> "452"
    message += b'452'
    
    # Field 2: Whitespace (constant, 1B) -> 0x20
    message += b'\x20'
    
    # Field 3: ReplyText (constant, 43B) -> exact ASCII text provided in IR
    message += b'Requested action not taken. Insufficient storage space in system.'
    
    # Field 4: EndOfLine (constant, 2B) -> CRLF 0x0D0A
    message += b'\x0d\x0a'
    
    return message