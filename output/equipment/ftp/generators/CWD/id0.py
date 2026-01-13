def generate_CWD():
    """Generate one CWD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    import random
    import string

    # Field 1: CommandCode (constant, 3B, value="CWD")
    message += b'CWD'

    # Field 2: Whitespace (constant, 1B, value=0x20)
    message += bytes([0x20])

    # Field 3: Pathname (variable, undefined length, printable ASCII excluding CR and LF)
    # Choose a reasonable length for the pathname (at least 1 char)
    valid_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure CR and LF are not present
    valid_chars = valid_chars.replace('\r', '').replace('\n', '')
    pathname_length = random.randint(1, 32)
    pathname = ''.join(random.choices(valid_chars, k=pathname_length))
    pathname_bytes = pathname.encode('ascii')
    message += pathname_bytes

    # Field 4: EndOfLine (constant, 2B, value=0x0D0A)
    message += bytes([0x0D, 0x0A])

    return message