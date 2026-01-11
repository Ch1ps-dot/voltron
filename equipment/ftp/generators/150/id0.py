def generate_150():
    """Generate one 150 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Constant field: ReplyCode (3 bytes) -> "150"
    reply_code = b'150'

    # Constant field: Whitespace (1 byte) -> 0x20 (space)
    whitespace = b'\x20'

    # Variable field: ReplyText (undefined length)
    # Allowed: ASCII printable 0x20-0x7E (exclude CR and LF)
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F))
    # Choose a reasonable length for a human-readable reply
    reply_length = random.randint(20, 60)
    reply_text_str = ''.join(random.choices(allowed_chars, k=reply_length))
    reply_text = reply_text_str.encode('ascii')

    # Constant field: EndOfLine (2 bytes) -> 0x0D0A (CR LF)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message += reply_code
    message += whitespace
    message += reply_text
    message += end_of_line

    return message