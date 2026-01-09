def input_init():
    """Generate one 451 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # ReplyCode: constant "451" (3 bytes)
    reply_code = b'451'
    
    # Whitespace: constant 0x20 (space)
    whitespace = b'\x20'
    
    # ReplyText: variable, ASCII excluding CR and LF, length chosen reasonably
    # Build allowed ASCII characters from 0x20 to 0x7E excluding CR(0x0D) and LF(0x0A)
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F) if c not in (0x0A, 0x0D))
    # Choose a reasonable length for a human-readable message
    text_length = random.randint(20, 60)
    reply_text_str = ''.join(random.choice(allowed_chars) for _ in range(text_length))
    reply_text = reply_text_str.encode('ascii')
    
    # EndOfLine: constant CR LF 0x0D0A
    end_of_line = b'\x0D\x0A'
    
    # Concatenate fields in exact order
    message = reply_code + whitespace + reply_text + end_of_line
    
    return message