def generate_REST():
    """Generate one REST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # Field 1: CommandCode (constant "REST", 4 bytes ASCII)
    command_code = b'REST'
    message += command_code

    # Field 2: SP (constant 0x20)
    sp = b'\x20'
    message += sp

    # Field 3: Marker (variable, decimal-integer ASCII digits, >= 0, undefined length)
    # Choose a reasonable non-negative integer value (e.g., up to 1 billion)
    marker_int = random.randint(0, 10**9)
    marker = str(marker_int).encode('ascii')
    message += marker

    # Field 4: CRLF (constant 0x0D0A)
    crlf = b'\x0d\x0a'
    message += crlf

    return message