def generate_STRU():
    """Generate one STRU message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # CommandCode (constant, 4B): 'STRU'
    message += b'STRU'
    
    # Whitespace (constant, 1B): 0x20 (space)
    message += b' '
    
    # StructureCode (variable, 1B): choose one of 'F', 'R', 'P'
    structure_char = random.choice(['F', 'R', 'P'])
    message += structure_char.encode('ascii')
    
    # EndOfLine (constant, 2B): 0x0D0A (CRLF)
    message += b'\r\n'
    
    return message