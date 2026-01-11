def generate_214():
    """Generate one 214 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant "214" ASCII)
    reply_code = b'214'

    # Field 2: Whitespace (constant 0x20)
    whitespace = b'\x20'

    # Field 3: ReplyText (variable, ASCII excluding CR, LF, undefined length)
    # Choose a reasonable length for a help message
    length = random.randint(10, 60)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure CR and LF are excluded (they are not in allowed_chars)
    reply_text_str = ''.join(random.choices(allowed_chars, k=length))
    reply_text = reply_text_str.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message += reply_code
    message += whitespace
    message += reply_text
    message += end_of_line

    return message