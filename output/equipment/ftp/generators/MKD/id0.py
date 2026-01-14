def generate_MKD():
    """Generate one MKD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # Field 1: CommandCode (constant "MKD")
    command_code = b'MKD'  # 3 bytes, ASCII

    # Field 2: Whitespace (constant 0x20)
    whitespace = b' '  # single SP

    # Field 3: Pathname (variable, ASCII excluding CR, LF)
    # Choose a reasonable pathname length and characters (no CR/LF).
    # Allow letters, digits, common path symbols, underscore, hyphen and slash.
    chars = string.ascii_letters + string.digits + "-_./ "
    # Ensure pathname length at least 1 and not excessively long
    pathname_length = random.randint(1, 20)
    # Generate pathname and ensure it contains no CR or LF
    pathname_str = ''.join(random.choices(chars, k=pathname_length))
    # Encode as ASCII bytes
    pathname = pathname_str.encode('ascii')

    # Field 4: EndOfLine (constant CRLF 0x0D0A)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in exact order
    message = command_code + whitespace + pathname + end_of_line

    return message