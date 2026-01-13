def generate_REST():
    """Generate one REST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode: constant "REST" (4 bytes ASCII)
    message += b'REST'

    # SP: single space 0x20
    message += b'\x20'

    # Marker: variable, ASCII decimal integer >= 0, length undefined -> choose a random non-negative integer
    marker_int = random.randint(0, 2**31 - 1)
    marker_bytes = str(marker_int).encode('ascii')
    message += marker_bytes

    # CRLF: constant 0x0D0A
    message += b'\x0d\x0a'

    return message