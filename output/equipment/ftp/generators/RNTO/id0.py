def generate_RNTO():
    """Generate one RNTO message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode (constant "RNTO")
    message += b'RNTO'
    
    # SP (single space 0x20)
    message += b' '
    
    # Pathname (variable, printable ASCII 0x20-0x7E excluding CR and LF)
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F) if i not in (0x0A, 0x0D))
    pathname_length = random.randint(1, 32)
    pathname = ''.join(random.choices(allowed_chars, k=pathname_length))
    message += pathname.encode('ascii')
    
    # CRLF (constant 0x0D0A)
    message += b'\r\n'
    
    return message