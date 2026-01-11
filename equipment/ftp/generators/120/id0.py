def generate_120():
    """Generate one 120 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    import random

    message = b''

    # ReplyCode: constant "120" (3 bytes)
    message += b'120'

    # Whitespace: constant 0x20 (1 byte)
    message += b'\x20'

    # ReplyText: variable, ASCII printable except CR, LF
    # Choose a human-readable representative text including an estimated minutes value.
    minutes = random.randint(1, 60)
    minute_word = "minute" if minutes == 1 else "minutes"
    reply_text = f"Service ready in {minutes} {minute_word}"
    # Encode as ASCII (guaranteed to contain no CR/LF)
    message += reply_text.encode('ascii')

    # EndOfLine: constant CR LF (0x0D 0x0A)
    message += b'\x0d\x0a'

    return message