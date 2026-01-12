def generate_125():
    """Generate one 125 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode: constant "125" (3 bytes)
    reply_code = b'125'
    
    # Whitespace: constant 0x20 (space)
    whitespace = bytes([0x20])
    
    # ReplyText: variable, ASCII excluding CR, LF. Choose a representative valid text.
    import random
    candidate_texts = [
        "Data connection already open; transfer starting",
        "Opening data connection; transfer starting",
        "File transfer starting"
    ]
    reply_text_str = random.choice(candidate_texts)
    # Ensure no CR or LF characters
    reply_text_str = reply_text_str.replace('\r', '').replace('\n', '')
    reply_text = reply_text_str.encode('ascii')
    
    # EndOfLine: constant 0x0D0A (CRLF)
    end_of_line = bytes([0x0D, 0x0A])
    
    # Concatenate fields in the order defined by the protoIR
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message