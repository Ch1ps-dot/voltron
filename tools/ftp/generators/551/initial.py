def input_init():
    """Generate one 551 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct fields in the order specified by the protoIR
    # ReplyCode: constant "551" (3 bytes)
    reply_code = b'551'
    
    # Whitespace1: constant 0x20 (space)
    whitespace1 = b'\x20'
    
    # ReplyText: constant "Requested action aborted. Page type unknown."
    reply_text = b'Requested action aborted. Page type unknown.'
    
    # EndOfLine: constant 0x0D0A (CRLF)
    end_of_line = b'\x0D\x0A'
    
    # Concatenate all fields into the final message bytes
    message = reply_code + whitespace1 + reply_text + end_of_line
    
    return message