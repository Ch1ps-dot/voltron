def generate_MODE():
    """Generate one MODE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # Field 1: CommandCode (constant, 4B) -> "MODE"
    message += b"MODE"
    
    # Field 2: Whitespace (constant, 1B) -> 0x20 (space)
    message += b"\x20"
    
    # Field 3: ModeCode (variable, 1B) -> one of 'S','B','C' (ASCII)
    mode_char = random.choice(['S', 'B', 'C'])
    message += mode_char.encode('ascii')
    
    # Field 4: EndOfLine (constant, 2B) -> 0x0D0A (CRLF)
    message += b"\x0D\x0A"
    
    return message