def generate_212():
    """Generate one 212 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # Field 1: ReplyCode (constant "212", 3 bytes)
    reply_code = b'212'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'  # space

    # Field 3: Text (variable, ASCII excluding CR, LF, length undefined)
    # Choose a reasonable random length and generate ASCII characters excluding CR and LF.
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    text_length = random.randint(10, 60)
    text_str = ''.join(random.choices(allowed_chars, k=text_length))
    # Ensure no CR or LF (just in case)
    text_str = text_str.replace('\r', ' ').replace('\n', ' ')
    text = text_str.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0D\x0A'  # CRLF

    # Concatenate fields in order
    message = reply_code + whitespace + text + end_of_line

    return message