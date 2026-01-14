def generate_PASV():
    """Generate one PASV message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode (constant, 4 bytes): "PASV"
    command_code = "PASV".encode('ascii')
    # Ensure it's exactly 4 bytes as specified
    if len(command_code) != 4:
        command_code = command_code[:4].ljust(4, b' ')
    message += command_code

    # EndOfLine (constant, 2 bytes): 0x0D0A (CRLF)
    end_of_line = bytes.fromhex('0D0A')
    message += end_of_line

    return message