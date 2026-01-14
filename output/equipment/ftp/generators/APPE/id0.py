def generate_APPE():
    """Generate one APPE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    import random
    import string

    message = b''

    # CommandCode: constant "APPE" (4 bytes)
    message += b'APPE'

    # Whitespace: single SP (0x20)
    message += b'\x20'

    # Pathname: variable, US-ASCII excluding CR(0x0D) and LF(0x0A)
    # Choose a reasonable length (1..32) and characters from printable ASCII (including space and punctuation)
    allowed_chars = ''.join(ch for ch in (string.ascii_letters + string.digits + string.punctuation + ' ') if ch not in '\r\n')
    pathname_length = random.randint(1, 32)
    # Ensure pathname does not consist solely of spaces (use at least one non-space if random chosen all spaces)
    pathname_chars = []
    for _ in range(pathname_length):
        pathname_chars.append(random.choice(allowed_chars))
    if all(c == ' ' for c in pathname_chars):
        # replace first char with a safe visible char
        pathname_chars[0] = random.choice(string.ascii_letters + string.digits + string.punctuation.replace('/', '') )
    pathname = ''.join(pathname_chars)
    # Encode as US-ASCII
    message += pathname.encode('ascii')

    # EndOfLine: CRLF (0x0D0A)
    message += b'\x0D\x0A'

    return message