def input_init():
    """Generate one 230 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: ReplyCode (constant, 3B, value="230")
    reply_code = b'230'  # three ASCII digits

    # Field 2: Whitespace (constant, 1B, value=0x20)
    whitespace = bytes([0x20])  # space

    # Field 3: ReplyText (variable, undefined length, ASCII excluding CR and LF)
    # Choose a representative, valid ASCII reply text (no CR or LF).
    possible_texts = [
        "User logged in, proceed",
        "Logged in successfully.",
        "User logged in.",
        "Welcome, user",
        "Login successful"
    ]
    reply_text_str = random.choice(possible_texts)
    reply_text = reply_text_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2B, value=0x0D0A)
    end_of_line = bytes.fromhex('0D0A')

    # Concatenate fields in order
    message = reply_code + whitespace + reply_text + end_of_line

    return message