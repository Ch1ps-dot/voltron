def input_init():
    """Generate one 221 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    import random
    import string

    # Field 1: ReplyCode (constant, 3B, value "221")
    message += b'221'

    # Field 2: Whitespace (constant, 1B, value 0x20)
    message += b' '

    # Field 3: ReplyText (variable, undefined length, ASCII excluding CR, LF)
    # Choose a reasonable random length (0 means omitted)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure CR and LF are not present
    allowed_chars = allowed_chars.replace('\r', '').replace('\n', '')
    text_length = random.randint(0, 50)  # reasonable length for a reply text
    if text_length > 0:
        reply_text = ''.join(random.choices(allowed_chars, k=text_length))
        # Encode as ASCII (characters chosen are ASCII)
        message += reply_text.encode('ascii')
    else:
        # Omitted reply text (empty)
        message += b''

    # Field 4: EndOfLine (constant, 2B, value 0x0D0A)
    message += b'\r\n'
    
    return message