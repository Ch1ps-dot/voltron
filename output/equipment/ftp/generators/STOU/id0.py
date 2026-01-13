def generate_STOU():
    """Generate one STOU message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant, 4B) value "STOU"
    message += b"STOU"
    
    # Field 2: EndOfLine (constant, 2B) value 0x0D0A (CRLF)
    message += bytes.fromhex("0D0A")
    
    return message