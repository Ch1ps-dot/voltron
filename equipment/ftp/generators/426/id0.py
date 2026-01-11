def generate_426():
    """Generate one 426 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: ReplyCode (constant, 3B) -> "426"
    reply_code = b'426'
    
    # Field 2: Whitespace (constant, 1B) -> 0x20 (space)
    whitespace = bytes.fromhex('20')
    
    # Field 3: ReplyText (constant, 35B) -> "Connection closed; transfer aborted."
    reply_text = "Connection closed; transfer aborted.".encode('ascii')
    
    # Field 4: EndOfLine (constant, 2B) -> 0x0D0A (CRLF)
    end_of_line = bytes.fromhex('0D0A')
    
    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message