def generate_PWD():
    """Generate one PWD message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant "PWD", 3 bytes, ASCII)
    command_code = b'PWD'
    message += command_code

    # Field 2: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0D\x0A'
    message += end_of_line

    return message