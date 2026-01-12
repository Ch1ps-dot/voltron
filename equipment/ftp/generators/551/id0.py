def generate_551():
    """Generate one 551 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode (constant "551", 3 bytes)
    message += b'551'
    
    # Whitespace1 (constant 0x20, 1 byte)
    message += b'\x20'
    
    # ReplyText (constant string, encoded as ASCII)
    message += b'Requested action aborted. Page type unknown.'
    
    # EndOfLine (constant 0x0D0A, CRLF, 2 bytes)
    message += bytes.fromhex('0D0A')
    
    return message