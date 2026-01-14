def generate_ABOR():
    """Generate one ABOR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    
    # Field 1: CommandCode (constant, 4 bytes) -> ASCII 'ABOR'
    message += b'ABOR'
    
    # Field 2: EndOfLine (constant, 2 bytes) -> 0x0D0A (CRLF)
    message += bytes.fromhex('0D0A')
    
    return message