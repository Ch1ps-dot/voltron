def input_init():
    """Generate one 553 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: ReplyCode (constant, 3 bytes) -> "553"
    reply_code = b'553'

    # Field 2: Whitespace (constant, 1 byte) -> 0x20 (space)
    whitespace = b'\x20'

    # Field 3: ReplyText (variable, undefined length) -> printable ASCII excluding CR, LF
    # Choose a representative, valid human-readable explanation (no CR/LF)
    possible_texts = [
        "Requested action not taken. File name not allowed.",
        "File name invalid or access condition prevents operation.",
        "Action aborted. Filename not allowed."
    ]
    reply_text_str = random.choice(possible_texts)
    reply_text = reply_text_str.encode('ascii')

    # Field 4: EndOfLine (constant, 2 bytes) -> 0x0D0A (CR LF)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in exact order
    message += reply_code
    message += whitespace
    message += reply_text
    message += end_of_line

    return message