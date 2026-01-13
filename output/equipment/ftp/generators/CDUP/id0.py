def generate_CDUP():
    """Generate one CDUP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: literal "CDUP" (4 ASCII characters)
    message += b'CDUP'
    
    # EndOfLine: CRLF sequence (0x0D0A)
    message += b'\x0D\x0A'
    
    return message