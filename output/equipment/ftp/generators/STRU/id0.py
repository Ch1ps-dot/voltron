def generate_STRU():
    """Generate one STRU message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode: constant "STRU" (4 bytes)
    message += b'STRU'

    # Whitespace: constant 0x20 (1 byte, space)
    message += bytes([0x20])

    # StructureCode: variable 1 byte, one of 'F', 'R', 'P'
    structure_code = random.choice(['F', 'R', 'P']).encode('ascii')
    message += structure_code

    # EndOfLine: constant CRLF (0x0D0A, 2 bytes)
    message += b'\x0D\x0A'

    return message