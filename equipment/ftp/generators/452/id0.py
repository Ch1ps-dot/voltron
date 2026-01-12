def generate_452():
    """Generate one 452 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct fields exactly as specified in the protoIR
    
    # ReplyCode: constant "452" (3 bytes)
    reply_code = b'452'
    
    # Whitespace: constant 0x20 (space, 1 byte)
    whitespace = b'\x20'
    
    # ReplyText: constant ASCII string (as given)
    reply_text = b'Requested action not taken. Insufficient storage space in system.'
    
    # EndOfLine: CRLF (0x0D0A, 2 bytes)
    end_of_line = b'\x0D\x0A'
    
    # Concatenate in the exact field order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message