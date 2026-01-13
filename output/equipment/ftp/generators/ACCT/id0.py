def generate_ACCT():
    """Generate one ACCT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    import random
    # CommandCode: constant "ACCT" (4 bytes ASCII)
    command = b'ACCT'
    
    # Whitespace: single space (0x20)
    whitespace = b'\x20'
    
    # AccountInformation: variable, printable US-ASCII 0x20-0x7E, excluding CR/LF.
    # Choose a reasonable length (1..32) and generate random printable characters.
    allowed_chars = ''.join(chr(c) for c in range(0x20, 0x7F))  # 0x20 .. 0x7E
    # CR (0x0D) and LF (0x0A) are outside this range but ensure exclusion if present
    allowed_chars = allowed_chars.replace('\r', '').replace('\n', '')
    acct_len = random.randint(1, 32)
    account_information = ''.join(random.choice(allowed_chars) for _ in range(acct_len)).encode('ascii')
    
    # EndOfLine: CRLF 0x0D0A
    eol = b'\x0d\x0a'
    
    # Concatenate fields in the exact order
    message = command + whitespace + account_information + eol
    
    return message