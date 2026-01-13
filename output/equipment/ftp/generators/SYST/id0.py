def generate_SYST():
    """Generate one SYST message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification

    # Field 1: CommandCode (constant, 4B, value="SYST")
    command_code = b'SYST'  # ASCII bytes for "SYST"
    message += command_code

    # Field 2: EndOfLine (constant, 2B, value="0x0D0A")
    end_of_line = bytes.fromhex('0D0A')  # CRLF
    message += end_of_line

    return message