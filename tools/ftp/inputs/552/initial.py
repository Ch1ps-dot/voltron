def input_init():
    """Generate one 552 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field 1: ReplyCode (constant, 3B) -> "552"
    reply_code = b'552'

    # Field 2: Whitespace (constant, 1B) -> 0x20 (space)
    whitespace = bytes([0x20])

    # Field 3: ReplyText (variable, undefined) -> ASCII excluding CR, LF
    # Choose a reasonable representative human-readable message
    candidates = [
        "Requested file action aborted. Exceeded storage allocation.",
        "Quota exceeded. Requested file action aborted.",
        "Requested file action aborted - storage allocation exceeded."
    ]
    reply_text = random.choice(candidates)
    # Encode as ASCII (ensures no CR/LF as candidates do not include them)
    reply_text_bytes = reply_text.encode('ascii')

    # Field 4: EndOfLine (constant, 2B) -> 0x0D0A (CR LF)
    end_of_line = bytes.fromhex('0D0A')

    # Concatenate fields in exact order
    message = reply_code + whitespace + reply_text_bytes + end_of_line

    return message