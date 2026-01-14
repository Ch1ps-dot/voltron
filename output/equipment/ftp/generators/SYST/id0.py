def generate_SYST():
    """Generate one SYST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant "SYST" (4 bytes, ASCII)
    message += b'SYST'
    
    # EndOfLine: constant 0x0D0A (CRLF)
    message += bytes.fromhex('0D0A')
    
    return message