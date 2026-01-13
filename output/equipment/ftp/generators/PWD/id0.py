def generate_PWD():
    """Generate one PWD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    
    # Field 1: CommandCode (constant, 3B, value "PWD")
    command_code = b'PWD'  # ASCII three-letter token
    
    # Field 2: EndOfLine (constant, 2B, value 0x0D0A -> CRLF)
    end_of_line = b'\x0D\x0A'
    
    message += command_code + end_of_line
    
    return message