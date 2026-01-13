def generate_SMNT():
    """Generate one SMNT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode: constant "SMNT" (4 bytes)
    message += b'SMNT'

    # Whitespace: constant 0x20 (1 byte)
    message += b'\x20'

    # Pathname: variable, ASCII excluding CR and LF, length undefined -> choose 1-64 bytes
    # Allowed bytes: 0x20 (space) through 0x7E (tilde), excluding 0x0A and 0x0D
    allowed_bytes = [c for c in range(0x20, 0x7F) if c not in (0x0A, 0x0D)]
    pathname_length = random.randint(1, 64)
    pathname_bytes = bytes(random.choices(allowed_bytes, k=pathname_length))
    message += pathname_bytes

    # EndOfLine: constant 0x0D0A (CR LF, 2 bytes)
    message += b'\x0D\x0A'

    return message