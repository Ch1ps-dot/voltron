def generate_STOU():
    """Generate one STOU message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant "STOU" (4 bytes ASCII)
    message += b"STOU"
    
    # EndOfLine: constant 0x0D0A (CRLF)
    message += bytes.fromhex("0D0A")
    
    return message