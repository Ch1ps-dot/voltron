def input_init():
    """Generate one 200 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    
    # ReplyCode: constant "200" (3 bytes)
    message += b'200'
    # Whitespace: constant 0x20 (space)
    message += b'\x20'
    # ReplyText: constant "Command okay"
    message += b'Command okay'
    # EndOfLine: constant CRLF 0x0D0A
    message += b'\x0D\x0A'
    
    return message