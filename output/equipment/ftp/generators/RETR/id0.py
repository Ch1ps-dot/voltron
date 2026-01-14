def generate_RETR():
    """Generate one RETR message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: CommandCode (constant "RETR", 4 bytes)
    command = b'RETR'

    # Field 2: Whitespace (one or more SP (0x20))
    # Choose a small random number of spaces to be compliant
    space_count = random.randint(1, 4)
    whitespace = b' ' * space_count

    # Field 3: Pathname (printable NVT-ASCII 0x20-0x7E excluding CR/LF), must be non-empty
    # Build allowed characters range
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F) if i not in (0x0A, 0x0D))
    pathname_length = random.randint(1, 32)
    pathname_str = ''.join(random.choice(allowed_chars) for _ in range(pathname_length))
    pathname = pathname_str.encode('ascii')

    # Field 4: EndOfLine (constant CR LF -> 0x0D0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message = command + whitespace + pathname + end_of_line

    return message