def generate_451():
    """Generate one 451 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # ReplyCode: constant "451" (3 bytes)
    reply_code = b'451'
    message += reply_code

    # Whitespace: constant 0x20 (space)
    message += b'\x20'

    # ReplyText: variable, ASCII excluding CR and LF
    # Choose a representative human-readable explanation
    candidates = [
        "Local processing error",
        "Requested action aborted: local error in processing",
        "Temporary server failure processing request",
        "File system error during operation",
        "Unexpected server error occurred"
    ]
    reply_text = random.choice(candidates)
    # Ensure ASCII encoding and no CR/LF
    reply_text_bytes = reply_text.encode('ascii', 'ignore')
    # (As a safeguard, remove any CR/LF if present)
    reply_text_bytes = reply_text_bytes.replace(b'\r', b'').replace(b'\n', b'')
    message += reply_text_bytes

    # EndOfLine: constant 0x0D0A (CRLF)
    message += b'\x0D\x0A'

    return message