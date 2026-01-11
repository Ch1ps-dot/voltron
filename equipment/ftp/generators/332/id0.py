def generate_332():
    """Generate one 332 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    import random

    # Field 1: ReplyCode (constant, 3 bytes) -> "332"
    message += b'332'

    # Field 2: Whitespace (constant, 1 byte) -> 0x20 (space)
    message += b'\x20'

    # Field 3: ReplyText (variable, undefined length) -> ASCII excluding CR, LF
    # Choose a reasonable random length and generate allowed ASCII characters (32..126) excluding CR/LF
    allowed_chars = ''.join(chr(c) for c in range(32, 127) if c not in (10, 13))
    text_length = random.randint(10, 40)  # reasonable length for a human-readable reply
    reply_text = ''.join(random.choices(allowed_chars, k=text_length))
    message += reply_text.encode('ascii')

    # Field 4: EndOfLine (constant, 2 bytes) -> 0x0D0A (CRLF)
    message += b'\x0d\x0a'

    return message