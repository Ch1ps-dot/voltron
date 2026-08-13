def generate() -> bytes:
    # Build the VRFY request according to RFC 5321
    # Fields: command (constant "VRFY"), separator (constant " "),
    # argument (variable, up to 505 octets), terminator (constant CRLF)
    
    # Choose a valid argument: a simple user name or email address
    # Common SMTP VRFY examples: "user", "postmaster", "user@domain"
    argument = b"user@example.org"
    
    # Ensure argument length does not exceed 505 octets (max 512 - 7)
    # Our argument is 17 bytes, well within limits
    
    # Assemble the request in IR order
    request = b"VRFY" + b" " + argument + b"\r\n"
    
    return request