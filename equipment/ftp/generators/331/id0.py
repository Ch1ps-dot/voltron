def generate_331():
    """Generate one 331 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # ReplyCode: constant "331" (3 bytes)
    reply_code = b'331'
    message += reply_code

    # Whitespace: constant 0x20 (1 byte)
    whitespace = bytes([0x20])
    message += whitespace

    # ReplyText: constant "User name okay, need password." (textual, ASCII)
    reply_text = b'User name okay, need password.'
    message += reply_text

    # EndOfLine: constant 0x0D0A (CRLF, 2 bytes)
    end_of_line = bytes.fromhex('0D0A')
    message += end_of_line

    return message