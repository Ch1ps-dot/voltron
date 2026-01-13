def generate_STOU():
    """Generate one STOU message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    # Field 1: CommandCode (constant, 4B) value "STOU"
    command_code = b"STOU"
    # Field 2: EndOfLine (constant, 2B) value 0x0D0A (CRLF)
    end_of_line = bytes.fromhex("0D0A")
    
    message = command_code + end_of_line
    
    return message