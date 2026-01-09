def input_init():
    """Generate one 503 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Field: StatusCode (constant, 3B) -> "503"
    message += b'503'

    # Field: Whitespace (constant, 1B) -> 0x20 (space)
    message += bytes([0x20])

    # Field: ExplanationText (variable, undefined length, ASCII excluding CR, LF)
    # Choose a reasonable human-readable explanation without CR/LF.
    explanations = [
        "Bad sequence of commands",
        "Command out of sequence",
        "Invalid command sequence",
        "Command not permitted in this state",
        "Sequence of commands not allowed"
    ]
    explanation = random.choice(explanations)
    # Ensure no CR or LF are present
    explanation = explanation.replace('\r', '').replace('\n', '')
    message += explanation.encode('ascii')

    # Field: EndOfLine (constant, 2B) -> 0x0D0A (CR LF)
    message += bytes.fromhex('0D0A')
    
    return message