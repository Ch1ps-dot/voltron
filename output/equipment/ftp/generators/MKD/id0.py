def generate_MKD():
    """Generate one MKD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: CommandCode (constant "MKD")
    command_code = b"MKD"

    # Field 2: Whitespace (constant 0x20)
    whitespace = b"\x20"

    # Field 3: Pathname (variable, ASCII excluding CR and LF, undefined length)
    # Choose a reasonable length between 1 and 32 bytes
    length = random.randint(1, 32)
    allowed_chars = string.ascii_letters + string.digits + "._-/" + " "
    # Build the pathname ensuring no CR or LF
    pathname_str = ''.join(random.choices(allowed_chars, k=length))
    pathname = pathname_str.encode('ascii')

    # Field 4: EndOfLine (constant CRLF 0x0D0A)
    end_of_line = b"\x0D\x0A"

    # Concatenate fields in exact order
    message += command_code
    message += whitespace
    message += pathname
    message += end_of_line

    return message