def generate_451():
    """Generate one 451 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random, string

    # ReplyCode: constant "451" (3 bytes)
    reply_code = b'451'

    # Whitespace: constant 0x20 (space)
    whitespace = b'\x20'

    # ReplyText: variable, ASCII excluding CR, LF, undefined length -> choose reasonable length
    # Build allowed ASCII printable characters excluding CR and LF
    printable = string.ascii_letters + string.digits + string.punctuation + ' '
    allowed_chars = [c for c in printable if c not in '\r\n']
    # Choose a reasonable length for human-readable message
    reply_text_len = random.randint(20, 60)
    reply_text_str = ''.join(random.choices(allowed_chars, k=reply_text_len))
    reply_text = reply_text_str.encode('ascii')

    # EndOfLine: constant CR LF 0x0D0A
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in the exact IR order
    message = reply_code + whitespace + reply_text + end_of_line

    return message