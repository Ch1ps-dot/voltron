def generate_200():
    """Generate one 200 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    # Field 1: ReplyCode (constant "200", 3B)
    reply_code = b"200"
    # Field 2: Whitespace (constant 0x20, 1B)
    whitespace = b"\x20"
    # Field 3: ReplyText (constant "Command okay", 10B in IR but emit exact value)
    reply_text = "Command okay".encode("ascii")
    # Field 4: EndOfLine (constant 0x0D0A, 2B)
    end_of_line = b"\x0d\x0a"
    
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message