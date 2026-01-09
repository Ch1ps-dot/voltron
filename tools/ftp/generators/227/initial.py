def input_init():
    """Generate one 227 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''

    # ReplyCode: constant "227"
    message += b'227'

    # Whitespace: single space 0x20
    message += b'\x20'

    # ReplyTextPrefix: constant "Entering Passive Mode ("
    message += "Entering Passive Mode (".encode('ascii')

    # Host octets: four variable decimal ASCII digits, 0-255
    host_octets = [random.randint(0, 255) for _ in range(4)]
    for i, octet in enumerate(host_octets, start=1):
        # HostOctetN
        message += str(octet).encode('ascii')
        # Comma separators after octet 1-3 and after octet4 (Comma4)
        if i <= 4:
            message += b','

    # Port bytes: two variable decimal ASCII digits, 0-255
    port_byte1 = random.randint(0, 255)
    port_byte2 = random.randint(0, 255)
    message += str(port_byte1).encode('ascii')
    # Comma5
    message += b','
    message += str(port_byte2).encode('ascii')

    # ReplyTextSuffix: closing parenthesis ')'
    message += b')'

    # OptionalComment: ASCII; may be empty — choose empty for a canonical response
    optional_comment = b''
    message += optional_comment

    # EndOfLine: CRLF 0x0D0A
    message += b'\x0D\x0A'

    return message