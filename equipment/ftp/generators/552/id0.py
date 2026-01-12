def generate_552():
    """Generate one 552 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct fields in the exact order from the protoIR:
    # 1) ReplyCode: constant "552" (3 bytes)
    reply_code = b'552'
    
    # 2) Whitespace: constant 0x20 (1 byte)
    whitespace = b' '
    
    # 3) ReplyText: variable, ASCII excluding CR, LF
    # Use the typical descriptive message for this reply code.
    reply_text_str = "Requested file action aborted. Exceeded storage allocation."
    reply_text = reply_text_str.encode('ascii')
    
    # 4) EndOfLine: constant 0x0D0A (2 bytes)
    end_of_line = b'\x0d\x0a'
    
    # Concatenate all parts into a single bytes object
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message