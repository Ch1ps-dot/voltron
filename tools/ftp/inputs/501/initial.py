def input_init():
    """Generate one 501 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: ReplyCode (constant "501", 3 bytes)
    reply_code = b'501'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = bytes([0x20])

    # Field 3: ReplyText (variable, ASCII printable characters excluding CR, LF)
    # Choose a reasonable length for the human-readable text
    length = random.randint(10, 60)
    # ASCII printable range 0x20 (space) to 0x7E (~), excluding CR(0x0D) and LF(0x0A)
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F) if i not in (0x0D, 0x0A))
    reply_text = ''.join(random.choices(allowed_chars, k=length))
    reply_text_bytes = reply_text.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in order
    message = reply_code + whitespace + reply_text_bytes + end_of_line

    return message