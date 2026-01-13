def generate_RMD():
    """Generate one RMD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: CommandCode (constant, 3B) -> "RMD"
    command = b'RMD'

    # Field 2: Separator (constant, 1B) -> 0x20 (space)
    separator = b'\x20'

    # Field 3: Pathname (variable, undefined length) -> ASCII excluding CR, LF
    # Choose a reasonable length and characters allowed by FTP pathname semantics.
    allowed = string.ascii_letters + string.digits + "/._- "  # spaces allowed; exclude CR and LF
    pathname_length = random.randint(1, 16)  # choose a reasonable length
    pathname_str = ''.join(random.choice(allowed) for _ in range(pathname_length))
    pathname = pathname_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2B) -> 0x0D0A (CRLF)
    eol = b'\x0d\x0a'

    # Concatenate fields in order
    message = command + separator + pathname + eol

    return message