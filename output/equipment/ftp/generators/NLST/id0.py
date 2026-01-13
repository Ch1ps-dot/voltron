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

    # We'll include an optional Pathname, so include the Whitespace (0x20)
    whitespace = b'\x20'

    # Pathname: variable, ASCII excluding CR and LF. Choose a reasonable length.
    # Allowed characters: letters, digits, and a small set of common pathname symbols.
    allowed_chars = string.ascii_letters + string.digits + "/._-~*?"
    # Ensure CR and LF are not in allowed_chars (they are not)
    pathname_length = random.randint(1, 24)
    pathname_str = ''.join(random.choices(allowed_chars, k=pathname_length))
    pathname_bytes = pathname_str.encode('ascii')

    # EndOfLine: constant CRLF (0x0D0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message = command_code + whitespace + pathname_bytes + end_of_line

    return message