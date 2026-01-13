def generate_HELP():
    """Generate one HELP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode (constant 4B "HELP")
    message += b'HELP'

    # Decide to include an argument for this instance (so SpaceIfArgument and ArgumentString will be present)
    include_argument = True

    if include_argument:
        # SpaceIfArgument (constant 1B 0x20)
        message += b'\x20'

        # ArgumentString (variable, NVT-ASCII printable characters 0x20-0x7E, excluding CR/LF)
        # Choose a reasonable length between 1 and 12
        allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F))
        arg_len = random.randint(1, 12)
        arg_str = ''.join(random.choice(allowed_chars) for _ in range(arg_len))
        # Encode as ASCII bytes
        message += arg_str.encode('ascii')

    # EndOfLine (constant 2B 0x0D0A)
    message += b'\x0D\x0A'

    return message