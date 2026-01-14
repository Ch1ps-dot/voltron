def generate_ACCT():
    """Generate one ACCT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random

    # CommandCode: 4-octet ASCII command verb "ACCT"
    command = b'ACCT'

    # Whitespace: single SPACE (0x20)
    whitespace = b'\x20'

    # AccountInformation: printable US-ASCII 0x20-0x7E, variable length (choose 1-32 bytes)
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F))  # 0x20 .. 0x7E
    acct_len = random.randint(1, 32)
    account_information = ''.join(random.choice(allowed_chars) for _ in range(acct_len)).encode('ascii')

    # EndOfLine: CRLF 0x0D0A
    eol = b'\x0d\x0a'

    message = command + whitespace + account_information + eol

    return message