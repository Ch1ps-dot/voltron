def generate_202():
    """Generate one 202 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode (constant, 3 bytes): "202"
    reply_code = b'202'
    
    # Whitespace (constant, 1 byte): 0x20 (space)
    whitespace = bytes([0x20])
    
    # ReplyText (constant, 38B per IR, value provided) - encode as ASCII
    reply_text = "Command not implemented, superfluous at this site.".encode('ascii')
    
    # EndOfLine (constant, 2 bytes): 0x0D0A (CR LF)
    end_of_line = b'\x0D\x0A'
    
    # Concatenate fields in the exact order specified by the IR
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message