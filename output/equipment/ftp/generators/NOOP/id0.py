def generate_NOOP():
    """Generate one NOOP message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode: constant 4B "NOOP" (ASCII)
    command_code = b'NOOP'
    
    # TelnetEndOfLine: constant 2B 0x0D0A (CRLF)
    telnet_eol = bytes.fromhex('0D0A')
    
    message += command_code
    message += telnet_eol
    
    return message