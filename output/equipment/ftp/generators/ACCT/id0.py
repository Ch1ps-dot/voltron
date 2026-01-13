def generate_ACCT():
    """Generate one ACCT message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    import random

    # Field 1: CommandCode (constant, 4B, value "ACCT")
    command_code = b'ACCT'

    # Field 2: Whitespace (constant, 1B, value 0x20)
    whitespace = b'\x20'  # SPACE

    # Field 3: AccountInformation (variable, undefined length)
    # Must be printable US-ASCII 0x20-0x7E (space to tilde), exclude CR and LF.
    allowed_chars = ''.join(chr(i) for i in range(0x20, 0x7F))
    # Choose a reasonable length for account information (e.g., 1 to 32 characters)
    acct_len = random.randint(1, 32)
    account_information = ''.join(random.choices(allowed_chars, k=acct_len)).encode('ascii')

    # Field 4: EndOfLine (constant, 2B, value 0x0D0A)
    end_of_line = b'\x0D\x0A'

    # Concatenate fields in exact order
    message += command_code
    message += whitespace
    message += account_information
    message += end_of_line

    return message