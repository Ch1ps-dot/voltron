def generate_502():
    """Generate one 502 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # Field 1: ReplyCode (constant "502", 3 bytes)
    reply_code = b'502'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = bytes([0x20])

    # Field 3: ReplyText (variable, ASCII excluding CR, LF, length undefined)
    # Choose a reasonable random length and generate ASCII printable characters
    # excluding CR (0x0D) and LF (0x0A). Use range 32-126 (printable ASCII).
    length = random.randint(10, 60)
    allowed_chars = ''.join(chr(c) for c in range(32, 127))  # 32..126 inclusive
    # Ensure exclusion of CR/LF (they are outside this range but kept for clarity)
    allowed_chars = allowed_chars.replace('\r', '').replace('\n', '')
    reply_text_str = ''.join(random.choices(allowed_chars, k=length))
    reply_text = reply_text_str.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = bytes.fromhex('0D0A')

    # Concatenate fields in order
    message = reply_code + whitespace + reply_text + end_of_line

    return message