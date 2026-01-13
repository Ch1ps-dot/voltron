def generate_REIN():
    """Generate one REIN message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant, 4B) -> ASCII "REIN"
    message += b'REIN'
    
    # Field 2: EndOfLine (constant, 2B) -> 0x0D0A (CR LF)
    message += bytes.fromhex('0D0A')
    
    return message