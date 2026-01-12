def generate_421():
    """Generate one 421 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    
    # ReplyCode: constant "421" (3 bytes)
    message += b'421'
    
    # Whitespace: constant 0x20 (1 byte)
    message += b'\x20'
    
    # ReplyText: variable, ASCII excluding CR, LF. Use a representative human-readable message.
    reply_text = "Service not available, closing control connection."
    reply_bytes = reply_text.encode('ascii')
    message += reply_bytes
    
    # EndOfLine: constant 0x0D0A (CRLF, 2 bytes)
    message += b'\x0d\x0a'
    
    return message