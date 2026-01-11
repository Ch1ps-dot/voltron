def generate_421():
    """Generate one 421 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # ReplyCode (constant, 3 bytes): "421"
    message += b'421'

    # Whitespace (constant, 1 byte): 0x20 (space)
    message += b'\x20'

    # ReplyText (variable, undefined length): ASCII excluding CR, LF
    # Choose a reasonable length for a human-readable message
    length = random.randint(20, 60)
    # Allowed ASCII printable range 0x20-0x7E (space through ~), which excludes CR (0x0D) and LF (0x0A)
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F))
    reply_text = ''.join(random.choices(allowed_chars, k=length))
    message += reply_text.encode('ascii')

    # EndOfLine (constant, 2 bytes): CRLF 0x0D0A
    message += b'\x0D\x0A'

    return message