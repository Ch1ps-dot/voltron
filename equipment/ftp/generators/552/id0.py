def generate_552():
    """Generate one 552 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # Field 1: ReplyCode (constant, 3 bytes) - value "552"
    message += b'552'

    # Field 2: Whitespace (constant, 1 byte) - space 0x20
    message += b' '

    # Field 3: ReplyText (variable, undefined length) - ASCII excluding CR, LF
    # Choose a reasonable representative human-readable message
    candidates = [
        "Requested file action aborted. Exceeded storage allocation.",
        "Requested file action aborted; storage allocation exceeded.",
        "Transfer aborted: storage quota exceeded."
    ]
    reply_text = random.choice(candidates)
    # Ensure ASCII and no CR/LF (candidates are safe)
    reply_bytes = reply_text.encode('ascii')

    message += reply_bytes

    # Field 4: EndOfLine (constant, 2 bytes) - CR LF 0x0D0A
    message += b'\r\n'

    return message