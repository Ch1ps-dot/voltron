def generate_225():
    """Generate one 225 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # ReplyCode (constant 3 bytes): "225"
    reply_code = b'225'
    
    # Whitespace (constant 1 byte): 0x20
    whitespace = bytes([0x20])
    
    # ReplyText (variable, undefined length): ASCII printable except CR, LF
    # Choose a reasonable length between 10 and 60 characters
    length = random.randint(10, 60)
    # ASCII printable range 0x20..0x7E inclusive
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7f) if chr(i) not in '\r\n')
    reply_text_str = ''.join(random.choice(allowed_chars) for _ in range(length))
    reply_text = reply_text_str.encode('ascii')
    
    # EndOfLine (constant 2 bytes): 0x0D0A
    end_of_line = bytes([0x0D, 0x0A])
    
    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message