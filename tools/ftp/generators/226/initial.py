def input_init():
    """Generate one 226 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # ReplyCode (constant "226", 3 bytes)
    message += b'226'
    
    # Whitespace (constant 0x20, 1 byte)
    message += b'\x20'
    
    # ReplyText (variable, ASCII printable excluding CR/LF, length undefined -> choose reasonable length)
    # Build list of printable ASCII characters from 0x20 to 0x7E inclusive
    chars = [chr(c) for c in range(0x20, 0x7F)]
    # Choose a reasonable length for the human-readable message
    text_length = random.randint(10, 30)
    reply_text = ''.join(random.choices(chars, k=text_length))
    message += reply_text.encode('ascii')
    
    # EndOfLine (constant 0x0D0A, 2 bytes)
    message += b'\x0D\x0A'
    
    return message