def input_init():
    """Generate one 125 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field: ReplyCode (constant 3B -> "125")
    reply_code = b'125'

    # Field: Whitespace (constant 1B -> 0x20)
    whitespace = bytes([0x20])

    # Field: ReplyText (variable, ASCII excluding CR, LF, length undefined)
    # Choose a representative human-readable reply text (RFC959 recommended text included)
    possible_texts = [
        "Data connection already open; transfer starting",
        "Opening data connection; starting transfer",
        "Transfer starting on data connection",
        "Data connection open; transfer commencing"
    ]
    reply_text_str = random.choice(possible_texts)
    # Ensure no CR or LF characters
    reply_text_str = reply_text_str.replace('\r', '').replace('\n', '')
    reply_text = reply_text_str.encode('ascii')

    # Field: EndOfLine (constant 2B -> 0x0D0A)
    end_of_line = bytes.fromhex('0D0A')

    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text + end_of_line

    return message