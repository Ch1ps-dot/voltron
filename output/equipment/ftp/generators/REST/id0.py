def generate_REST():
    """Generate one REST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    import random

    # CommandCode: constant "REST" (4 bytes ASCII)
    command = b'REST'

    # SP: constant 0x20 (single space)
    sp = bytes([0x20])

    # Marker: variable, decimal-integer (ASCII digits '0'-'9'), >= 0
    # Length is undefined; choose a reasonable value within protocol conventions
    marker_value = random.randint(0, 1000000)  # choose a non-negative integer
    marker = str(marker_value).encode('ascii')

    # CRLF: constant 0x0D0A
    crlf = bytes([0x0d, 0x0a])

    message = command + sp + marker + crlf

    return message