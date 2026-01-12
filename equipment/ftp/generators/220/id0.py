def generate_220():
    """Generate one 220 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # Field: ReplyCode (constant 3B = "220")
    message += b'220'

    # Field: Whitespace (constant 1B = 0x20)
    message += b' '

    # Field: ReplyText (variable, undefined length)
    # Must be ASCII printable characters and space, without CR or LF.
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Choose a reasonable length for a greeting text
    reply_length = random.randint(10, 50)
    # Generate the textual greeting
    reply_text = ''.join(random.choice(allowed_chars) for _ in range(reply_length))
    # Ensure ASCII encoding
    reply_text_bytes = reply_text.encode('ascii')
    message += reply_text_bytes

    # Field: EndOfLine (constant 2B = 0x0D0A)
    message += b'\r\n'
    
    return message