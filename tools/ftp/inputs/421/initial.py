def input_init():
    """Generate one 421 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # ReplyCode (constant: "421")
    message += b'421'

    # Whitespace (constant: 0x20)
    message += bytes([0x20])

    # ReplyText (variable: ASCII excluding CR, LF; undefined length -> choose a reasonable length)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    allowed_chars = allowed_chars.replace('\r', '').replace('\n', '')
    # Choose a reasonable length for a human-readable message (e.g., between 20 and 80 chars)
    reply_length = random.randint(20, 80)
    reply_text = ''.join(random.choice(allowed_chars) for _ in range(reply_length))
    message += reply_text.encode('ascii')

    # EndOfLine (constant: 0x0D0A)
    message += bytes.fromhex('0D0A')
    
    return message