def generate_202():
    """Generate one 202 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field: ReplyCode (constant, 3B) -> "202"
    reply_code = b"202"
    
    # Field: Whitespace (constant, 1B) -> 0x20 (space)
    whitespace = b"\x20"
    
    # Field: ReplyText (constant, 38B) -> "Command not implemented, superfluous at this site."
    # Emit the exact constant value as ASCII bytes
    reply_text = b"Command not implemented, superfluous at this site."
    
    # Field: EndOfLine (constant, 2B) -> 0x0D0A (CR LF)
    end_of_line = b"\x0D\x0A"
    
    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message