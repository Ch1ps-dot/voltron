def generate_452():
    """Generate one 452 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Fields as specified in the protoIR, in order.
    ReplyCode = b'452'  # constant, 3 bytes
    Whitespace = b'\x20'  # constant, 1 byte (space)
    ReplyText = b'Requested action not taken. Insufficient storage space in system.'  # constant text
    EndOfLine = b'\x0D\x0A'  # constant CRLF, 2 bytes

    message = ReplyCode + Whitespace + ReplyText + EndOfLine

    return message