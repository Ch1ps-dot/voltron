def generate_PASV():
    """Generate one PASV message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant "PASV" (4 bytes, ASCII)
    message += b'PASV'
    
    # EndOfLine: constant 0x0D0A (CRLF, 2 bytes)
    message += bytes.fromhex('0D0A')
    
    return message