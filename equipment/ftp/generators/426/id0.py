def generate_426():
    """Generate one 426 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # According to protoIR:
    # 1) ReplyCode: constant "426" (3 bytes)
    reply_code = b'426'
    
    # 2) Whitespace: constant 0x20 (1 byte)
    whitespace = b'\x20'
    
    # 3) ReplyText: constant "Connection closed; transfer aborted." (textual, ASCII)
    reply_text = b'Connection closed; transfer aborted.'
    
    # 4) EndOfLine: constant 0x0D0A (CRLF, 2 bytes)
    end_of_line = b'\x0d\x0a'
    
    # Concatenate in the exact field order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message