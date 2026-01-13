def generate_QUIT():
    """Generate one QUIT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant, 4B) -> "QUIT"
    message += b'QUIT'
    
    # Field 2: EndOfLine (constant, 2B) -> CRLF 0x0D0A
    message += b'\x0D\x0A'
    
    return message