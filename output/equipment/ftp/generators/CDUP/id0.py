def generate_CDUP():
    """Generate one CDUP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant "CDUP", 4 ASCII bytes)
    command_code = b'CDUP'
    
    # Field 2: EndOfLine (constant CRLF, 2 bytes 0x0D0A)
    end_of_line = b'\x0D\x0A'
    
    # Concatenate fields in the exact order
    message = command_code + end_of_line
    
    return message