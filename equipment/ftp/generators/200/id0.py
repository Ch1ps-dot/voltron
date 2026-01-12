def generate_200():
    """Generate one 200 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: ReplyCode (constant "200", 3 bytes)
    reply_code = b'200'
    
    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'
    
    # Field 3: ReplyText (constant "Command okay")
    # Emit the exact constant value as bytes (ASCII)
    reply_text = b'Command okay'
    
    # Field 4: EndOfLine (constant 0x0D0A, CRLF)
    end_of_line = b'\x0D\x0A'
    
    # Concatenate fields in the order specified by the protoIR
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message