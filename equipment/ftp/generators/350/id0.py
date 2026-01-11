def generate_350():
    """Generate one 350 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # ReplyCode: constant "350" (3 bytes)
    message += b'350'

    # Whitespace: constant 0x20
    message += b'\x20'

    # ReplyText: variable, ASCII displayable characters excluding CR and LF
    # Use a realistic FTP reply text chosen at random from common phrases
    choices = [
        "File exists, ready for destination name",
        "Rename from <name> to <name> - specify destination",
        "Pending further information",
        "Rename command accepted, awaiting destination name"
    ]
    reply_text = random.choice(choices)

    # Ensure ASCII encoding
    reply_bytes = reply_text.encode('ascii')
    message += reply_bytes

    # EndOfLine: constant CRLF 0x0D0A
    message += b'\x0D\x0A'

    return message