def generate_227():
    """Generate one 227 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''

    # ReplyCode (constant "227")
    message += b'227'

    # Whitespace (constant 0x20)
    message += b'\x20'

    # ReplyTextPrefix (constant "Entering Passive Mode (")
    message += b'Entering Passive Mode ('

    # HostOctet1 (variable 0-255, decimal ASCII)
    host_octet1 = random.randint(0, 255)
    message += str(host_octet1).encode('ascii')

    # Comma1 (constant ',')
    message += b','

    # HostOctet2 (variable 0-255)
    host_octet2 = random.randint(0, 255)
    message += str(host_octet2).encode('ascii')

    # Comma2
    message += b','

    # HostOctet3
    host_octet3 = random.randint(0, 255)
    message += str(host_octet3).encode('ascii')

    # Comma3
    message += b','

    # HostOctet4
    host_octet4 = random.randint(0, 255)
    message += str(host_octet4).encode('ascii')

    # Comma4
    message += b','

    # PortByte1 (high byte, 0-255)
    port_byte1 = random.randint(0, 255)
    message += str(port_byte1).encode('ascii')

    # Comma5
    message += b','

    # PortByte2 (low byte, 0-255)
    port_byte2 = random.randint(0, 255)
    message += str(port_byte2).encode('ascii')

    # ReplyTextSuffix (constant ')')
    message += b')'

    # OptionalComment (variable ASCII; may be empty)
    # Randomly choose to include a comment or not
    if random.choice([True, False]):
        # generate a short ASCII comment, prefix with a space
        comment_length = random.randint(5, 20)
        allowed = string.ascii_letters + string.digits + ' '
        comment_body = ''.join(random.choice(allowed) for _ in range(comment_length))
        if not comment_body.startswith(' '):
            comment_body = ' ' + comment_body
        message += comment_body.encode('ascii')

    # EndOfLine (constant 0x0D0A)
    message += b'\x0D\x0A'

    return message