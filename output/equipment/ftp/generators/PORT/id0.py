def generate_PORT():
    """Generate one PORT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode: constant "PORT" (4 bytes)
    message += b'PORT'

    # SP: single space (0x20)
    message += b'\x20'

    # Generate IP octets h1-h4 as ASCII decimal (0-255). Choose 1-254 to avoid special addresses.
    h1 = random.randint(1, 254)
    h2 = random.randint(1, 254)
    h3 = random.randint(1, 254)
    h4 = random.randint(1, 254)

    # Append h1, Comma1, h2, Comma2, h3, Comma3, h4, Comma4
    message += str(h1).encode('ascii')
    message += b'\x2C'  # Comma1 ','
    message += str(h2).encode('ascii')
    message += b'\x2C'  # Comma2 ','
    message += str(h3).encode('ascii')
    message += b'\x2C'  # Comma3 ','
    message += str(h4).encode('ascii')
    message += b'\x2C'  # Comma4 ','

    # Port: choose a port in the server's configured data port range (1024-65535)
    port = random.randint(1024, 65535)
    p1 = port // 256  # high-order byte (0-255)
    p2 = port % 256   # low-order byte (0-255)

    # Append p1, Comma5, p2
    message += str(p1).encode('ascii')
    message += b'\x2C'  # Comma5 ','
    message += str(p2).encode('ascii')

    # EndOfLine: CR LF (0x0D 0x0A)
    message += b'\x0D\x0A'

    return message