def generate_PWD():
    """Generate one PWD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant "PWD" (3 bytes, ASCII)
    message += b'PWD'
    
    # EndOfLine: constant CRLF (0x0D0A, 2 bytes)
    message += bytes.fromhex('0D0A')
    
    return message