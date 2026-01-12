def generate_226():
    """Generate one 226 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # Field 1: ReplyCode (constant "226", 3 bytes)
    message += b'226'
    
    # Field 2: Whitespace (constant 0x20, 1 byte)
    message += b'\x20'
    
    # Field 3: ReplyText (variable, ASCII printable excluding CR/LF, length undefined)
    # Choose a reasonable length between 10 and 30 characters.
    printable_chars = string.ascii_letters + string.digits + string.punctuation + ' '
    # Ensure CR and LF are not included (they aren't in printable_chars here).
    length = random.randint(10, 30)
    reply_text = ''.join(random.choices(printable_chars, k=length))
    # Encode as ASCII
    message += reply_text.encode('ascii', errors='ignore')
    
    # Field 4: EndOfLine (constant 0x0D0A, 2 bytes)
    message += b'\x0D\x0A'
    
    return message