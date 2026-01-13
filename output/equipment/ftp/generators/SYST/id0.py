def generate_SYST():
    """Generate one SYST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    # Field 1: CommandCode (constant "SYST", 4 bytes)
    message += b"SYST"
    # Field 2: EndOfLine (constant 0x0D0A, CRLF, 2 bytes)
    message += bytes.fromhex('0D0A')
    
    return message