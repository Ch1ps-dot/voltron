def generate_551():
    """Generate one 551 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field: ReplyCode (constant, 3B, value "551")
    message += b'551'
    
    # Field: Whitespace1 (constant, 1B, value 0x20)
    message += b'\x20'
    
    # Field: ReplyText (constant, 33B, value "Requested action aborted. Page type unknown.")
    # Emit the exact string value encoded in ASCII
    message += b'Requested action aborted. Page type unknown.'
    
    # Field: EndOfLine (constant, 2B, value 0x0D0A)
    message += b'\x0D\x0A'
    
    return message