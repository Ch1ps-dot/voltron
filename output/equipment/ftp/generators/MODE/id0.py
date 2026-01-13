def generate_MODE():
    """Generate one MODE message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    import random

    message = b''
    
    # Field 1: CommandCode (constant, 4B) -> "MODE"
    command_code = b"MODE"
    message += command_code

    # Field 2: Whitespace (constant, 1B) -> 0x20 (space)
    whitespace = b"\x20"
    message += whitespace

    # Field 3: ModeCode (variable, 1B) -> one of 'S', 'B', 'C' (ASCII)
    mode_choice = random.choice(['S', 'B', 'C'])
    mode_code = mode_choice.encode('ascii')
    message += mode_code

    # Field 4: EndOfLine (constant, 2B) -> CRLF 0x0D0A
    end_of_line = b"\x0D\x0A"
    message += end_of_line

    return message