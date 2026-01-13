def generate_NLST():
    """Generate one NLST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # CommandCode: constant "NLST" (4 bytes)
    command_code = b'NLST'
    message += command_code

    # Pathname: optional; generate a valid ASCII pathname excluding CR and LF.
    # We'll include a pathname in this instance.
    allowed_chars = string.ascii_letters + string.digits + "/._-*"
    pathname_length = random.randint(1, 32)  # reasonable variable length
    pathname_str = ''.join(random.choice(allowed_chars) for _ in range(pathname_length))
    pathname_bytes = pathname_str.encode('ascii')

    # Whitespace: present because pathname is included (single SP, 0x20)
    whitespace = b'\x20'
    message += whitespace

    # Pathname field (variable, ASCII excluding CR and LF)
    message += pathname_bytes

    # EndOfLine: CRLF (0x0D0A)
    end_of_line = b'\x0d\x0a'
    message += end_of_line

    return message