def generate_REIN():
    """Generate one REIN message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant 4B value "REIN"
    command_code = b'REIN'
    message += command_code

    # EndOfLine: constant 2B value 0x0D0A (CR LF)
    end_of_line = bytes.fromhex('0D0A')
    message += end_of_line

    return message