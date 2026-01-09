def input_init():
    """Generate one 500 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: ReplyCode (constant "500", 3 bytes)
    message += b'500'
    
    # Field 2: Whitespace (constant 0x20)
    message += b'\x20'
    
    # Field 3: ReplyText (variable, ASCII printable characters excluding CR, LF)
    # Use a representative human-readable explanation for a 500 FTP reply.
    reply_text = "Syntax error, command unrecognized."
    # Encode as ASCII bytes
    message += reply_text.encode('ascii')
    
    # Field 4: EndOfLine (constant 0x0D0A)
    message += b'\x0d\x0a'
    
    return message