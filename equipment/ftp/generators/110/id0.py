def generate_110():
    """Generate one 110 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    import string

    # Field: ReplyCode (constant "110")
    message += b'110'

    # Field: Whitespace (constant 0x20)
    message += bytes([0x20])

    # Field: MarkerText (variable, ASCII excluding CR, LF, length undefined)
    # Choose a reasonable representative length and generate ASCII chars excluding CR and LF.
    allowed_chars = (
        string.ascii_letters + string.digits + string.punctuation + string.whitespace
    )
    # Remove CR and LF explicitly if present
    allowed_chars = ''.join(ch for ch in allowed_chars if ch not in '\r\n')

    # Choose a length between 1 and 40 for the marker text
    marker_length = random.randint(1, 40)
    marker_text = ''.join(random.choice(allowed_chars) for _ in range(marker_length))
    # Ensure ASCII encoding
    marker_bytes = marker_text.encode('ascii', errors='ignore')
    # If encoding dropped characters (unlikely), ensure at least one byte
    if len(marker_bytes) == 0:
        marker_bytes = b'Marker1'
    message += marker_bytes

    # Field: EndOfLine (constant 0x0D0A)
    message += bytes.fromhex('0D0A')

    return message