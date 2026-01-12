def generate_214():
    """Generate one 214 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Constant: ReplyCode "214" (ASCII)
    reply_code = b'214'

    # Constant: Whitespace (space, 0x20)
    whitespace = b'\x20'

    # Variable: ReplyText (ASCII excluding CR, LF), length undefined -> choose reasonable length
    # Build allowed ASCII characters excluding CR and LF
    allowed_chars = ''.join(c for c in (string.ascii_letters + string.digits + string.punctuation + ' ') if c not in '\r\n')
    reply_text_length = random.randint(20, 60)  # reasonable help message length
    reply_text_str = ''.join(random.choices(allowed_chars, k=reply_text_length))
    reply_text = reply_text_str.encode('ascii')

    # Constant: EndOfLine CR LF (0x0D0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message = reply_code + whitespace + reply_text + end_of_line

    return message