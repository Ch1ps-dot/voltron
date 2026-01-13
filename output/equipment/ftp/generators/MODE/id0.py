def generate_MODE():
    """Generate one MODE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # CommandCode: constant "MODE" (4 bytes ASCII)
    message += b"MODE"

    # Whitespace: constant 0x20 (single space)
    message += b"\x20"

    # ModeCode: variable 1B, one of 'S', 'B', 'C' (ASCII)
    mode = random.choice(['S', 'B', 'C'])
    message += mode.encode('ascii')

    # EndOfLine: constant CRLF 0x0D0A
    message += b"\x0D\x0A"
    
    return message