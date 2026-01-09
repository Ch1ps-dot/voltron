def input_init():
    """Generate one 257 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # Field 1: ReplyCode (constant "257", 3 bytes)
    reply_code = b'257'

    # Field 2: Whitespace (constant 0x20, 1 byte)
    whitespace = b'\x20'

    # Field 3: Pathname (variable, ASCII, typically enclosed in double quotes)
    # Construct a reasonable random pathname, e.g., "/home/user/docs"
    num_components = random.randint(1, 4)
    comp_chars = string.ascii_letters + string.digits + "-._"
    components = []
    for _ in range(num_components):
        L = random.randint(1, 10)
        comp = ''.join(random.choices(comp_chars, k=L))
        components.append(comp)
    pathname_str = "/" + "/".join(components)
    # Enclose in double quotes per common FTP reply format
    pathname_bytes = b'"' + pathname_str.encode('ascii') + b'"'

    # Field 4: OptionalText (variable, ASCII excluding CR, LF). May be omitted.
    include_optional = random.choice([True, False])
    if include_optional:
        # Generate a short human-readable message without CR or LF
        text_chars = string.ascii_letters + string.digits + " .,_-:()[]"
        text_len = random.randint(5, 30)
        optional_text_str = ''.join(random.choices(text_chars, k=text_len))
        optional_text_bytes = optional_text_str.encode('ascii')
        # Must be separated from pathname by a single space
        optional_field = b' ' + optional_text_bytes
    else:
        optional_field = b''

    # Field 5: EndOfLine (constant 0x0D0A, CRLF)
    end_of_line = b'\x0d\x0a'

    # Concatenate fields in the exact order
    message = reply_code + whitespace + pathname_bytes + optional_field + end_of_line

    return message