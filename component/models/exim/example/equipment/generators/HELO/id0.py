def generate() -> bytes:
    """
    Generate a valid SMTP HELO request.
    """
    # Constants as per IR table
    verb = b"HELO"
    sp = b" "
    crlf = b"\r\n"
    
    # Domain: a valid domain per RFC 5321 Section 4.1.2
    # Use a common example domain that is valid and variable-length
    domain = b"example.com"
    
    # Build the message in IR order: verb, SP, domain, CRLF
    # Total command line length must be <= 512 octets including CRLF
    # Our constructed message: 4 (HELO) + 1 (space) + len(domain) + 2 (CRLF) = 7 + len(domain)
    # For domain "example.com" (11 bytes), total = 18 bytes, well within limit.
    return verb + sp + domain + crlf