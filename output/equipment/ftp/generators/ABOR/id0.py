def generate_ABOR():
    """Generate one ABOR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field: CommandCode (constant "ABOR", 4 bytes ASCII)
    message += b'ABOR'
    
    # Field: EndOfLine (constant 0x0D0A, CRLF)
    message += b'\x0D\x0A'
    
    return message