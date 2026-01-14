def generate_REIN():
    """Generate one REIN message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant "REIN", 4 bytes ASCII)
    message += b'REIN'
    
    # Field 2: EndOfLine (constant CR LF, 0x0D0A, 2 bytes)
    message += b'\x0D\x0A'
    
    return message