def generate_RMD():
    """Generate one RMD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: CommandCode (constant, 3B, value "RMD")
    command_code = b'RMD'

    # Field 2: Separator (constant, 1B, value 0x20 -> space)
    separator = b' '

    # Field 3: Pathname (variable, undefined length, ASCII excluding CR, LF)
    # Choose a reasonable length and characters allowed by the comment.
    # We'll allow letters, digits, common pathname chars, spaces, dots, underscores, hyphens and slashes.
    allowed_chars = string.ascii_letters + string.digits + " ./_-"
    # Ensure length at least 1 and not excessively long
    path_len = random.randint(1, 32)
    pathname_str = ''.join(random.choices(allowed_chars, k=path_len))
    # Ensure CR and LF are not present (they are not in allowed_chars)
    pathname = pathname_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2B, value 0x0D0A -> CRLF)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in the exact order
    message += command_code
    message += separator
    message += pathname
    message += end_of_line

    return message