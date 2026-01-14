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

    # Field 1: CommandCode (constant "CWD", 3 bytes)
    message += b"CWD"

    # Field 2: Whitespace (constant 0x20, 1 byte)
    message += b"\x20"

    # Field 3: Pathname (variable, printable ASCII excluding CR and LF, length undefined but >=1)
    # Build an allowed character set: letters, digits, punctuation and space (exclude CR and LF)
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + " "
    # Choose a reasonable length for the pathname (1..24)
    pathname_len = random.randint(1, 24)
    pathname_str = "".join(random.choice(allowed_chars) for _ in range(pathname_len))
    # Encode as ASCII bytes (CR and LF are excluded by construction)
    message += pathname_str.encode("ascii")

    # Field 4: EndOfLine (constant CRLF 0x0D0A, 2 bytes)
    message += b"\x0d\x0a"

    return message