def input_init():
    """Generate one 331 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode (constant, 3B): "331"
    message += b'331'
    
    # Whitespace (constant, 1B): 0x20 (space)
    message += bytes([0x20])
    
    # ReplyText (constant, 22B per IR but emit the exact provided value): "User name okay, need password."
    message += "User name okay, need password.".encode('ascii')
    
    # EndOfLine (constant, 2B): 0x0D0A (CRLF)
    message += bytes.fromhex('0d0a')
    
    return message