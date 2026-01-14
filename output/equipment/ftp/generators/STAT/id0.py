def generate_STAT():
    """Generate one STAT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # CommandCode (constant "STAT")
    message += b'STAT'

    # Construct a valid Pathname (ASCII excluding CR and LF).
    # Choose a representative pathname starting with '/' and containing safe characters.
    allowed_chars = string.ascii_letters + string.digits + '._-'
    num_components = random.randint(1, 4)  # 1-4 path components
    components = []
    for _ in range(num_components):
        comp_len = random.randint(1, 12)  # each component 1-12 chars
        comp = ''.join(random.choice(allowed_chars) for _ in range(comp_len))
        components.append(comp)
    pathname = '/' + '/'.join(components)

    # Whitespace (0x20) is required because Pathname is present
    message += b'\x20'

    # Pathname (ASCII)
    message += pathname.encode('ascii')

    # EndOfLine (CRLF)
    message += b'\x0D\x0A'

    return message