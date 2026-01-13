def generate_PORT():
    """Generate one PORT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode (constant "PORT")
    message += b'PORT'

    # SP (0x20)
    message += b'\x20'

    # h1,h2,h3,h4 : each ASCII decimal 0-255
    h1 = random.randint(0, 255)
    message += str(h1).encode('ascii')

    # Comma1 (0x2C)
    message += b','

    h2 = random.randint(0, 255)
    message += str(h2).encode('ascii')

    # Comma2
    message += b','

    h3 = random.randint(0, 255)
    message += str(h3).encode('ascii')

    # Comma3
    message += b','

    h4 = random.randint(0, 255)
    message += str(h4).encode('ascii')

    # Comma4
    message += b','

    # p1 and p2 derived from a random port (0-65535)
    port = random.randint(0, 65535)
    p1 = (port >> 8) & 0xFF
    p2 = port & 0xFF

    message += str(p1).encode('ascii')

    # Comma5
    message += b','

    message += str(p2).encode('ascii')

    # EndOfLine (CR LF -> 0x0D0A)
    message += b'\x0D\x0A'

    return message