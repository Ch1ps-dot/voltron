def generate_150():
    """Generate one 150 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # Constant: 3-digit reply code '150'
    reply_code = b'150'  # length 3B, value "150"

    # Constant: single whitespace (space)
    whitespace = b'\x20'  # length 1B, value 0x20

    # Variable: ReplyText (ASCII printable 0x20-0x7E), choose a reasonable random length
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F))  # space through '~'
    reply_length = random.randint(20, 60)  # choose a reasonable length
    reply_text = ''.join(random.choice(allowed_chars) for _ in range(reply_length))
    reply_text_bytes = reply_text.encode('ascii')

    # Constant: End of line CR LF
    end_of_line = b'\x0D\x0A'  # length 2B, value 0x0D0A

    # Concatenate fields in the exact order
    message = reply_code + whitespace + reply_text_bytes + end_of_line

    return message