def generate_CWD():
    """Generate one CWD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # CommandCode: constant "CWD" (3 bytes ASCII)
    command = b'CWD'

    # Whitespace: single SPACE (0x20)
    whitespace = b' '

    # Pathname: variable, printable ASCII and permitted path characters excluding CR and LF
    # Choose a reasonable length between 1 and 64 (required field)
    allowed_chars = string.ascii_letters + string.digits + "/._- ~"
    length = random.randint(1, 64)
    pathname_str = ''.join(random.choices(allowed_chars, k=length))
    pathname = pathname_str.encode('ascii')

    # EndOfLine: CRLF (0x0D0A)
    eol = b'\r\n'

    # Concatenate fields in the exact order
    message = command + whitespace + pathname + eol

    return message