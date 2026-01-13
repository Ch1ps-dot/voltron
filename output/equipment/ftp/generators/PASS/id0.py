def generate_PASS():
    """Generate one PASS message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: CommandCode (constant, 4B) -> "PASS"
    command_code = b'PASS'

    # Field 2: Whitespace (constant, 1B) -> 0x20 (SP)
    whitespace = b'\x20'

    # Field 3: Password (variable, undefined length)
    # Printable NVT-ASCII characters (0x20..0x7E), excluding CR (0x0D) and LF (0x0A).
    # May be empty. Choose a reasonable length between 0 and 12.
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F))  # 0x20..0x7E
    pwd_length = random.randint(0, 12)
    password_str = ''.join(random.choice(allowed_chars) for _ in range(pwd_length))
    password = password_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2B) -> 0x0D0A (CR LF)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in order
    message = command_code + whitespace + password + end_of_line

    return message