def input_init():
    """Generate one 214 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # ReplyCode: constant "214" (3 bytes)
    message += b'214'

    # Whitespace: constant 0x20 (1 byte)
    message += b' '

    # ReplyText: variable, ASCII excluding CR and LF, length undefined -> choose a reasonable length
    # Build a charset excluding CR and LF
    charset = ''.join(ch for ch in (string.ascii_letters + string.digits + string.punctuation + ' ') if ch not in '\r\n')
    reply_length = random.randint(10, 60)  # choose a reasonable length for a help message
    reply_text = ''.join(random.choice(charset) for _ in range(reply_length))
    message += reply_text.encode('ascii')

    # EndOfLine: constant 0x0D0A (CRLF, 2 bytes)
    message += b'\r\n'
    
    return message