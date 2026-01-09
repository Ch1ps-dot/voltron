def input_init():
    """Generate one 110 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant "110", 3 bytes)
    reply_code = b'110'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'

    # Field 3: MarkerText (variable, ASCII excluding CR and LF)
    # Choose a reasonable length for the marker text
    marker_length = random.randint(5, 20)
    # Build allowed ASCII characters excluding CR and LF
    allowed_chars = ''.join(ch for ch in string.printable if ch not in '\r\n')
    marker_text_str = ''.join(random.choice(allowed_chars) for _ in range(marker_length))
    marker_text = marker_text_str.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in the exact order
    message = reply_code + whitespace + marker_text + end_of_line

    return message