def input_init():
    """Generate one 530 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification

    # ReplyCode: constant "530" (3 bytes)
    message += b'530'

    # Whitespace: constant 0x20 (space)
    message += b'\x20'

    # MessageText: variable, ASCII excluding CR, LF
    # Use a representative human-readable explanation
    message_text = 'Not logged in.'
    # Encode as ASCII (no CR or LF included)
    message += message_text.encode('ascii')

    # EndOfLine: constant 0x0D0A
    message += b'\x0d\x0a'
    
    return message