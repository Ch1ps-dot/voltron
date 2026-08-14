import struct

def generate() -> bytes:
    # verb: constant "EHLO" (canonical uppercase)
    verb = b"EHLO"
    # SP: single ASCII space separator
    sp = b" "
    # client-domain: variable; choose a valid domain name for state exploration
    # Common valid values: "example.com", "localhost", "client.example"
    # Use a boundary/typical value: a short domain like "ex.com"
    client_domain = b"ex.com"
    # CRLF: end-of-line marker
    crlf = b"\r\n"
    
    # Concatenate in IR order: verb, SP, client-domain, CRLF
    message = verb + sp + client_domain + crlf
    return message