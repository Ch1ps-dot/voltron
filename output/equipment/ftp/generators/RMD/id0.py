def generate_RMD():
    """Generate one RMD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    import random
    import string

    message = b''

    # CommandCode: constant "RMD" (3 bytes)
    message += b'RMD'

    # Separator: single SPACE (0x20)
    message += b'\x20'

    # Pathname: variable, ASCII excluding CR and LF, choose a reasonable length
    # Allowed characters: letters, digits, common pathname symbols, and space
    allowed_chars = string.ascii_letters + string.digits + "-_./ "
    pathname_length = random.randint(1, 32)  # reasonable length for a pathname
    pathname = ''.join(random.choices(allowed_chars, k=pathname_length))
    # Ensure pathname is not all spaces (still valid per spec but undesirable)
    if pathname.strip() == '':
        pathname = 'dir' + pathname[0: max(0, pathname_length - 3)]
    message += pathname.encode('ascii')

    # EndOfLine: CRLF (0x0D0A)
    message += b'\x0d\x0a'

    return message