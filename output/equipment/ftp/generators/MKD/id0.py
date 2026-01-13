def generate_MKD():
    """Generate one MKD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: CommandCode (constant, 3B) -> "MKD"
    command_code = b"MKD"

    # Field 2: Whitespace (constant, 1B) -> 0x20 (space)
    whitespace = bytes([0x20])

    # Field 3: Pathname (variable, undefined) -> ASCII excluding CR and LF
    # Choose a reasonable random length between 1 and 32 and characters safe for filenames
    min_len = 1
    max_len = 32
    pathname_length = random.randint(min_len, max_len)
    allowed_chars = string.ascii_letters + string.digits + "/._-"
    pathname_str = ''.join(random.choices(allowed_chars, k=pathname_length))
    pathname = pathname_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2B) -> CRLF 0x0D0A
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message += command_code
    message += whitespace
    message += pathname
    message += end_of_line

    return message