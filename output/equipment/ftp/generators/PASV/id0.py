def generate_PASV():
    """Generate one PASV message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Field 1: CommandCode (constant "PASV", 4 bytes, ASCII)
    command_code = b'PASV'
    message += command_code

    # Field 2: EndOfLine (constant 0x0D0A, CRLF, 2 bytes)
    end_of_line = bytes.fromhex('0D0A')
    message += end_of_line

    return message