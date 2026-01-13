def generate_QUIT():
    """Generate one QUIT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant "QUIT" (4 ASCII bytes)
    command_code = "QUIT".encode('ascii')
    # EndOfLine: constant 0x0D0A (CRLF)
    end_of_line = bytes.fromhex('0D0A')
    
    # Serialize fields in order
    message += command_code
    message += end_of_line
    
    return message