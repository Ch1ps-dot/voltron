def generate_ABOR():
    """Generate one ABOR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant ASCII 'ABOR' (4 bytes)
    message += b'ABOR'
    
    # EndOfLine: constant CRLF (0x0D0A)
    message += bytes.fromhex('0d0a')
    
    return message