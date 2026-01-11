def generate_230():
    """Generate one 230 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # ReplyCode: constant "230" (3 bytes)
    reply_code = b'230'

    # Whitespace: single space 0x20
    whitespace = b'\x20'

    # ReplyText: ASCII, excluding CR and LF.
    # Choose a reasonable representative reply text commonly used by FTP servers.
    possible_texts = [
        "User logged in, proceed",
        "Login successful",
        "User logged in",
        "Logged in successfully, proceed",
        "User logged in, proceed."
    ]
    reply_text_str = random.choice(possible_texts)
    # Encode as ASCII (no CR or LF present in the chosen strings)
    reply_text = reply_text_str.encode('ascii')

    # EndOfLine: CR LF (0x0D0A)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in the exact order specified by the protoIR
    message = reply_code + whitespace + reply_text + end_of_line

    return message