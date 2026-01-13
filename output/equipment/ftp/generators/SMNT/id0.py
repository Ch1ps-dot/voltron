def generate_SMNT():
    """Generate one SMNT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode: constant "SMNT" (4 bytes ASCII)
    message += b'SMNT'

    # Whitespace: single space (0x20)
    message += bytes([0x20])

    # Pathname: variable, ASCII printable characters excluding CR and LF.
    # Choose a reasonable length between 1 and 64 and start with '/' to form a typical pathname.
    length = random.randint(1, 64)
    # Generate printable US-ASCII range 0x20 (space) to 0x7E (~)
    printable = ''.join(chr(i) for i in range(0x20, 0x7F))
    if length == 1:
        pathname = '/'
    else:
        # Ensure no CR/LF (they are not in the printable range selected)
        pathname = '/' + ''.join(random.choice(printable) for _ in range(length - 1))
    message += pathname.encode('ascii')

    # EndOfLine: CR LF (0x0D 0x0A)
    message += b'\r\n'

    return message