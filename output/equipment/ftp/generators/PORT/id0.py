def generate_PORT():
    """Generate one PORT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # CommandCode (constant "PORT")
    message += b'PORT'

    # SP (space)
    message += b' '

    # h1..h4: IP address octets (ASCII decimal 0-255)
    h1 = random.randint(0, 255)
    h2 = random.randint(0, 255)
    h3 = random.randint(0, 255)
    h4 = random.randint(0, 255)

    message += str(h1).encode('ascii')
    message += b','
    message += str(h2).encode('ascii')
    message += b','
    message += str(h3).encode('ascii')
    message += b','
    message += str(h4).encode('ascii')
    message += b','

    # p1 and p2: derive from a realistic TCP port (choose within 1024-65535),
    # then split into high-order and low-order bytes
    port = random.randint(1024, 65535)
    p1 = port // 256
    p2 = port % 256

    message += str(p1).encode('ascii')
    message += b','
    message += str(p2).encode('ascii')

    # EndOfLine (CRLF)
    message += b'\r\n'

    return message