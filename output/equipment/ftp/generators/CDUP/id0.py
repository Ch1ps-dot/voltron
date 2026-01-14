def generate_CDUP():
    """Generate one CDUP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant "CDUP" (4 ASCII characters)
    command_code = b'CDUP'
    
    # EndOfLine: constant CRLF (0x0D0A)
    end_of_line = bytes.fromhex('0D0A')
    
    # Serialize fields in the order defined by the protoIR
    message = command_code + end_of_line
    
    return message