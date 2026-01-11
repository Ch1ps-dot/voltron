def generate_227():
    """Generate one 227 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random
    import string

    message = b''
    
    # 1. ReplyCode: constant "227"
    message += b'227'

    # 2. Whitespace: constant 0x20
    message += b'\x20'

    # 3. ReplyTextPrefix: constant "Entering Passive Mode ("
    message += b'Entering Passive Mode ('

    # 4. HostOctet1: variable decimal ASCII digits 0-255
    host_octet1 = random.randint(0, 255)
    message += str(host_octet1).encode('ascii')

    # 5. Comma1: constant ','
    message += b'\x2C'

    # 6. HostOctet2: variable decimal ASCII digits 0-255
    host_octet2 = random.randint(0, 255)
    message += str(host_octet2).encode('ascii')

    # 7. Comma2: constant ','
    message += b'\x2C'

    # 8. HostOctet3: variable decimal ASCII digits 0-255
    host_octet3 = random.randint(0, 255)
    message += str(host_octet3).encode('ascii')

    # 9. Comma3: constant ','
    message += b'\x2C'

    # 10. HostOctet4: variable decimal ASCII digits 0-255
    host_octet4 = random.randint(0, 255)
    message += str(host_octet4).encode('ascii')

    # 11. Comma4: constant ','
    message += b'\x2C'

    # 12-14. Port bytes: choose a valid port and split into two bytes (high, low)
    port = random.randint(1025, 65535)
    port_byte1 = port // 256
    port_byte2 = port % 256

    # 12. PortByte1: variable decimal ASCII digits 0-255
    message += str(port_byte1).encode('ascii')

    # 13. Comma5: constant ','
    message += b'\x2C'

    # 14. PortByte2: variable decimal ASCII digits 0-255
    message += str(port_byte2).encode('ascii')

    # 15. ReplyTextSuffix: constant ')'
    message += b'\x29'

    # 16. OptionalComment: ASCII; may be empty. Randomly include a short comment or leave empty.
    if random.choice([True, False]):
        # generate a short comment of 5-20 printable ASCII characters (excluding control)
        length = random.randint(5, 20)
        # use letters, digits, spaces and common punctuation
        chars = string.ascii_letters + string.digits + ' ,-._/()'
        comment = ' ' + ''.join(random.choices(chars, k=length))
        message += comment.encode('ascii')
    else:
        # empty comment
        message += b''

    # 17. EndOfLine: constant CRLF 0x0D0A
    message += b'\x0D\x0A'
    
    return message