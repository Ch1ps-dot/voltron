def input_init():
    """Generate one 250 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # ReplyCode: constant "250" (3 bytes)
    reply_code = b'250'

    # Whitespace: constant 0x20 (space)
    whitespace = bytes([0x20])

    # ReplyText: variable, ASCII excluding CR and LF, undefined length -> choose a reasonable length
    # Build a plausible human-readable explanatory text by joining random words (no CR/LF)
    words = [
        "Requested", "file", "action", "okay", "completed", "Transfer", "successful",
        "directory", "created", "deleted", "stored", "retrieved", "ready", "done", "status"
    ]
    num_words = random.randint(3, 7)
    reply_text_str = ' '.join(random.choice(words) for _ in range(num_words))
    if random.choice([True, False]):
        reply_text_str += '.'
    # Ensure only ASCII characters and explicitly exclude CR and LF
    reply_text_bytes = reply_text_str.encode('ascii', errors='ignore')

    # EndOfLine: constant 0x0D0A (CRLF)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text_bytes + end_of_line

    return message