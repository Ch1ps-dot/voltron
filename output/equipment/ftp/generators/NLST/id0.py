def generate_NLST():
    """Generate one NLST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    # Field 1: CommandCode (constant "NLST")
    command_code = b'NLST'

    # Decide to include an optional Pathname (so Whitespace must be present)
    include_pathname = True

    # Field 2: Whitespace (constant 0x20) - present only if Pathname follows
    whitespace = b' ' if include_pathname else b''

    # Field 3: Pathname (variable, ASCII excluding CR and LF, undefined length)
    if include_pathname:
        # choose a reasonable length between 1 and 20
        length = random.randint(1, 20)
        # allowed ASCII characters excluding CR (0x0D) and LF (0x0A)
        extra_symbols = "/.-_~*?[]()"
        allowed_chars = string.ascii_letters + string.digits + extra_symbols + ' '
        # generate the pathname string and encode as ASCII
        pathname_str = ''.join(random.choice(allowed_chars) for _ in range(length))
        pathname = pathname_str.encode('ascii')
    else:
        pathname = b''

    # Field 4: EndOfLine (constant CRLF 0x0D0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message = command_code + whitespace + pathname + end_of_line

    return message