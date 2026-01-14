def generate_SMNT():
    """Generate one SMNT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # CommandCode: constant "SMNT" (4 bytes)
    message += b'SMNT'

    # Whitespace: single space (0x20)
    message += b'\x20'

    # Pathname: variable, printable US-ASCII excluding CR and LF.
    # Choose a reasonable length between 1 and 32 and make it a pathname starting with '/'.
    allowed_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure CR and LF are not present (they are not in allowed_chars as constructed)
    length = random.randint(1, 32)
    if length == 1:
        pathname = '/'
    else:
        # first char '/' to resemble a pathname, rest random from allowed set
        rest = ''.join(random.choice(allowed_chars) for _ in range(length - 1))
        pathname = '/' + rest

    # Encode as ASCII bytes
    pathname_bytes = pathname.encode('ascii', errors='ignore')
    message += pathname_bytes

    # EndOfLine: CR LF (0x0D0A)
    message += b'\x0d\x0a'
    
    return message