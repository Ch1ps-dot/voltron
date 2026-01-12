def generate_230():
    """Generate one 230 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # Field 1: ReplyCode (constant "230", 3 bytes)
    message += b'230'
    
    # Field 2: Whitespace (constant 0x20, 1 byte)
    message += b'\x20'
    
    # Field 3: ReplyText (variable, ASCII excluding CR and LF, length undefined)
    # Choose a reasonable representative reply text used by FTP servers.
    reply_options = [
        "User logged in, proceed",
        "User logged in.",
        "Logged in successfully",
        "Login successful, proceed",
        "User logged in; transfer starting"
    ]
    reply_text = random.choice(reply_options)
    # Ensure no CR/LF characters are present (they are not in our options)
    reply_bytes = reply_text.encode('ascii')
    message += reply_bytes
    
    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    message += b'\x0D\x0A'
    
    return message