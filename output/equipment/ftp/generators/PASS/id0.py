def generate_PASS():
    """Generate one PASS message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # CommandCode (constant, 4 bytes): "PASS"
    command_code = b'PASS'
    message += command_code

    # Whitespace (constant, 1 byte): 0x20 (SP)
    message += b'\x20'

    # Password (variable, undefined length): use the known SUT password for user 'ubuntu'
    # Must be printable NVT-ASCII excluding CR (0x0D) and LF (0x0A)
    password_str = 'ubuntu'
    password_bytes = password_str.encode('ascii')
    # Ensure it does not contain CR or LF
    if b'\r' in password_bytes or b'\n' in password_bytes:
        # Fallback to empty password if invalid (should not happen for 'ubuntu')
        password_bytes = b''
    message += password_bytes

    # EndOfLine (constant, 2 bytes): CR LF (0x0D 0x0A)
    message += b'\x0d\x0a'
    
    return message