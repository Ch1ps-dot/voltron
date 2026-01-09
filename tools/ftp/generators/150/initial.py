def input_init():
    """Generate one 150 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    # Constant ReplyCode: '150'
    reply_code = b'150'
    # Constant Whitespace: 0x20
    whitespace = b'\x20'
    # Variable ReplyText: ASCII printable (0x20-0x7E), may exclude CR, LF
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F))
    # Choose a reasonable length for the human-readable reply
    reply_length = random.randint(20, 60)
    reply_text_str = ''.join(random.choices(allowed_chars, k=reply_length))
    reply_text = reply_text_str.encode('ascii')
    # Constant EndOfLine: CR LF (0x0D0A)
    end_of_line = b'\x0D\x0A'
    # Construct message in the exact field order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message