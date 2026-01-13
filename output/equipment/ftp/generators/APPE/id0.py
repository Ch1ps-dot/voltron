def generate_APPE():
    """Generate one APPE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # CommandCode (constant "APPE")
    command = b'APPE'

    # Whitespace (constant 0x20)
    whitespace = b'\x20'

    # Pathname (variable, US-ASCII excluding CR, LF, length undefined -> choose reasonable length)
    # Use printable US-ASCII range 0x20..0x7E (space through ~), which excludes CR (0x0D) and LF (0x0A)
    min_len = 1
    max_len = 64
    pathname_len = random.randint(min_len, max_len)
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F))
    pathname_str = ''.join(random.choice(allowed_chars) for _ in range(pathname_len))
    pathname = pathname_str.encode('ascii')

    # EndOfLine (constant 0x0D0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in exact order
    message = command + whitespace + pathname + end_of_line

    return message