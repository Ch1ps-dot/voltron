def generate_425():
    """Generate one 425 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct fields in exact order from protoIR:
    # ReplyCode (constant "425", 3B)
    reply_code = b"425"
    # Whitespace (constant 0x20, 1B)
    whitespace = b"\x20"
    # ReplyText (constant "Can't open data connection.", 28B as specified)
    reply_text = b"Can't open data connection."
    # EndOfLine (constant 0x0D0A, 2B)
    end_of_line = b"\x0D\x0A"
    
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message