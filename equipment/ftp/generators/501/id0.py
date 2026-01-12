def generate_501():
    """Generate one 501 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field 1: ReplyCode (constant "501", 3 bytes)
    reply_code = b'501'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'  # ASCII space

    # Field 3: ReplyText (variable, undefined length, ASCII printable characters excluding CR, LF)
    # Choose a reasonable length for human-readable explanatory text
    length = random.randint(20, 60)
    # ASCII printable range 0x20-0x7E
    printable_chars = ''.join(chr(i) for i in range(0x20, 0x7F))
    # Ensure CR and LF are excluded (they are outside 0x20-0x7E, but enforce exclusion if present)
    printable_chars = printable_chars.replace('\r', '').replace('\n', '')
    reply_text_str = ''.join(random.choices(printable_chars, k=length))
    # Make the text readable by ensuring it starts with a typical explanation phrase
    prefix = "Syntax error, "
    # Trim or pad to keep overall length reasonable while keeping randomness
    if len(prefix) < length:
        reply_text_str = prefix + reply_text_str[len(prefix):]
    else:
        reply_text_str = prefix[:length]
    reply_text = reply_text_str.encode('ascii')

    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    end_of_line = b'\x0D\x0A'  # CR LF

    # Concatenate fields in order
    message = reply_code + whitespace + reply_text + end_of_line

    return message