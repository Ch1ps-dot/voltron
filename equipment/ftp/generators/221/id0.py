def generate_221():
    """Generate one 221 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant "221", 3 bytes)
    reply_code = b'221'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'

    # Field 3: ReplyText (variable, ASCII excluding CR, LF, length undefined)
    # Choose a reasonable random length (0..24). May be empty.
    reply_len = random.randint(0, 24)
    # Allowed ASCII characters from 32 to 126 (printable), excluding CR(13) and LF(10)
    allowed_chars = ''.join(chr(i) for i in range(32, 127) if i not in (10, 13))
    if reply_len == 0:
        reply_text_bytes = b''
    else:
        reply_text = ''.join(random.choices(allowed_chars, k=reply_len))
        reply_text_bytes = reply_text.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, CRLF, 2 bytes)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in exact order
    message = reply_code + whitespace + reply_text_bytes + end_of_line

    return message