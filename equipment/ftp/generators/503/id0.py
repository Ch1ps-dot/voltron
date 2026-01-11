def generate_503():
    """Generate one 503 message for the ftp protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # StatusCode (constant, 3B): "503"
    message += b'503'
    
    # Whitespace (constant, 1B): 0x20 (space)
    message += b'\x20'
    
    # ExplanationText (variable, undefined): ASCII excluding CR, LF
    # Use a representative human-readable explanation.
    explanation_text = "Bad sequence of commands."
    message += explanation_text.encode('ascii')
    
    # EndOfLine (constant, 2B): 0x0D0A (CRLF)
    message += b'\x0D\x0A'
    
    return message