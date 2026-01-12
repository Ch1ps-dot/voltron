def generate_500():
    """Generate one 500 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode: constant "500" (3 bytes)
    reply_code = b'500'
    
    # Whitespace: constant 0x20 (space, 1 byte)
    whitespace = bytes([0x20])
    
    # ReplyText: variable, ASCII printable characters excluding CR and LF.
    # Use a representative human-readable explanation for the error.
    reply_text_str = "Syntax error, command unrecognized."
    # Encode as ASCII bytes
    reply_text = reply_text_str.encode('ascii')
    
    # EndOfLine: constant 0x0D0A (CR LF, 2 bytes)
    end_of_line = bytes([0x0D, 0x0A])
    
    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message