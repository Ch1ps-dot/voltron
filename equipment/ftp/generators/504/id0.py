def generate_504():
    """Generate one 504 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: ReplyCode (constant, 3 bytes) -> "504"
    reply_code = b'504'
    message += reply_code

    # Field 2: Whitespace (constant, 1 byte) -> 0x20 (space)
    whitespace = b'\x20'
    message += whitespace

    # Field 3: ReplyText (variable, undefined length) -> use a typical human-readable ASCII message
    reply_text_str = "Command not implemented for that parameter."
    reply_text = reply_text_str.encode('ascii')
    message += reply_text

    # Field 4: EndOfLine (constant, 2 bytes) -> CR LF (0x0D0A)
    end_of_line = b'\x0D\x0A'
    message += end_of_line

    return message