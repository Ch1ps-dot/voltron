def generate_PASS():
    """Generate one PASS message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # CommandCode: constant "PASS" (4 bytes, ASCII)
    command = b'PASS'

    # Whitespace: single space (0x20)
    whitespace = bytes([0x20])

    # Password: variable, printable NVT-ASCII characters excluding CR (0x0D) and LF (0x0A); may be empty
    # Choose a reasonable length between 0 and 16 (inclusive)
    pwd_length = random.randint(0, 16)
    allowed_chars = [chr(i) for i in range(0x20, 0x7F) if i not in (0x0A, 0x0D)]
    password_str = ''.join(random.choices(allowed_chars, k=pwd_length))
    password = password_str.encode('ascii')

    # EndOfLine: CR LF (0x0D 0x0A)
    eol = bytes([0x0D, 0x0A])

    # Concatenate fields in the exact order
    message = command + whitespace + password + eol

    return message