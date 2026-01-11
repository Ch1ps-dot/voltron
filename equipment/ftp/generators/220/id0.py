def generate_220():
    """Generate one 220 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    import random

    # ReplyCode: constant 3 bytes, value "220"
    reply_code = b'220'

    # Whitespace: constant 1 byte, value 0x20 (space)
    whitespace = bytes([0x20])

    # ReplyText: variable length (undefined)
    # Allowed: ASCII printable characters and space (0x20..0x7E), excluding CR/LF
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F))
    # Choose a reasonable random length for a greeting text
    reply_text_length = random.randint(10, 50)
    reply_text_str = ''.join(random.choices(allowed_chars, k=reply_text_length))
    reply_text = reply_text_str.encode('ascii')

    # EndOfLine: constant 2 bytes, value 0x0D0A (CR LF)
    end_of_line = bytes([0x0D, 0x0A])

    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text + end_of_line

    return message