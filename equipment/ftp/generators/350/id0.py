def generate_350():
    """Generate one 350 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # Field: ReplyCode (constant, 3B) -> "350"
    reply_code = b'350'

    # Field: Whitespace (constant, 1B) -> 0x20 (space)
    whitespace = b'\x20'

    # Field: ReplyText (variable, undefined) -> ASCII displayable characters excluding CR, LF
    # Choose a reasonable length between 10 and 60 characters
    min_len = 10
    max_len = 60
    length = random.randint(min_len, max_len)
    # Allowed characters: printable ASCII excluding CR and LF
    allowed_chars = ''.join(ch for ch in (string.ascii_letters + string.digits + string.punctuation + ' ') if ch not in '\r\n')
    reply_text_str = ''.join(random.choice(allowed_chars) for _ in range(length))
    # Ensure the text is displayable and readable by optionally starting with a capital letter
    if reply_text_str and reply_text_str[0] not in string.ascii_letters:
        reply_text_str = 'A' + reply_text_str[1:]
    reply_text = reply_text_str.encode('ascii')

    # Field: EndOfLine (constant, 2B) -> 0x0D0A (CRLF)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in order
    message = reply_code + whitespace + reply_text + end_of_line

    return message