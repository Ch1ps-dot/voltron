def input_init():
    """Generate one 426 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification

    # Field 1: ReplyCode (constant, 3B, value "426")
    message += b'426'

    # Field 2: Whitespace (constant, 1B, value 0x20)
    message += b'\x20'

    # Field 3: ReplyText (constant, 35B, value "Connection closed; transfer aborted.")
    # Emit the exact ASCII text as bytes
    message += b'Connection closed; transfer aborted.'

    # Field 4: EndOfLine (constant, 2B, value 0x0D0A)
    message += b'\x0D\x0A'

    return message