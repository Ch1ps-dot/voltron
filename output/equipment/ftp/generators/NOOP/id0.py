def generate_NOOP():
    """Generate one NOOP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant 4-byte ASCII 'NOOP'
    command_code = b'NOOP'
    
    # TelnetEndOfLine: constant 2-byte CRLF (0x0D0A)
    telnet_eol = bytes.fromhex('0D0A')
    
    message += command_code + telnet_eol
    
    return message