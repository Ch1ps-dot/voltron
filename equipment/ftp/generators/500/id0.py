def generate_500():
    """Generate one 500 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # ReplyCode: constant "500" (3 bytes)
    reply_code = b'500'

    # Whitespace: single space (0x20)
    whitespace = b'\x20'

    # ReplyText: ASCII printable characters excluding CR, LF
    # Choose a reasonable length for a human-readable explanation (e.g., 10-60 chars)
    length = random.randint(10, 60)
    printable_chars = [chr(i) for i in range(32, 127)]  # ASCII 32..126 inclusive
    reply_text_str = ''.join(random.choice(printable_chars) for _ in range(length))
    reply_text = reply_text_str.encode('ascii')

    # EndOfLine: CR LF (0x0D 0x0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text + end_of_line

    return message