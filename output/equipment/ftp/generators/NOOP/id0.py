def generate_NOOP():
    """Generate one NOOP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant, 4B) -> ASCII "NOOP"
    message += b'NOOP'
    
    # Field 2: TelnetEndOfLine (constant, 2B) -> 0x0D0A (CRLF)
    message += bytes.fromhex('0D0A')
    
    return message