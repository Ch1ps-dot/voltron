def generate_STRU():
    """Generate one STRU message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode: constant 'STRU' (4 bytes)
    message += b'STRU'
    
    # Whitespace: constant single space (0x20)
    message += b'\x20'
    
    # StructureCode: variable 1 byte, choose among 'F', 'R', 'P'
    structure_code = random.choice(['F', 'R', 'P'])
    message += structure_code.encode('ascii')
    
    # EndOfLine: constant CRLF (0x0D0A)
    message += b'\x0D\x0A'
    
    return message