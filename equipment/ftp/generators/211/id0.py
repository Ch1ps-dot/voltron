def generate_211():
    """Generate one 211 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # ReplyCode: constant "211" (3 bytes)
    reply_code = b'211'

    # Separator: constant space (0x20, 1 byte)
    separator = b'\x20'

    # Text: variable, ASCII excluding CR and LF, length undefined -> choose a reasonable length
    # Generate a random ASCII text between 10 and 60 characters excluding CR (\r) and LF (\n)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure CR and LF are not in allowed_chars (they are not in string.* sets), but filter defensively
    allowed_chars = ''.join(c for c in allowed_chars if c not in '\r\n')
    text_length = random.randint(10, 60)
    text_str = ''.join(random.choices(allowed_chars, k=text_length))
    text = text_str.encode('ascii')

    # EndOfLine: constant CR LF (0x0D0A, 2 bytes)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in exact order
    message = reply_code + separator + text + end_of_line

    return message