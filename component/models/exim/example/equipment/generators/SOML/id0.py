import random

def generate() -> bytes:
    # Build a valid SOML command per RFC 5321
    # command verb: "SOML" (4 bytes, uppercase)
    # separator: single space
    # FROM: keyword: "FROM:" (5 bytes, uppercase)
    # reverse-path: either "<>" (null) or a valid path
    #   valid path: "<" [ A-d-l ":" ] Mailbox ">"
    #   A-d-l: "@" domain (possibly multiple with comma)
    #   Mailbox: Local-part "@" domain
    #   Here we use simple valid examples
    # CRLF: "\r\n"
    
    # Choose a random reverse-path style
    choice = random.choice(["null", "simple", "with_at_domain"])
    
    if choice == "null":
        reverse_path = b"<>"
    elif choice == "simple":
        # Local-part (no special chars, <=64) and domain (simple)
        local = random.choice(["user", "test", "alice", "bob", "admin"])
        domain = random.choice(["example.com", "test.org", "mail.example"])
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    else:  # with_at_domain
        # A-d-l: one or more "@" domain elements
        at_domain = b"@" + random.choice(["relay1.com", "mx1.test", "gateway.org"]).encode()
        local = random.choice(["user", "test", "alice"])
        domain = random.choice(["example.com", "test.org"])
        reverse_path = b"<" + at_domain + b":" + local.encode() + b"@" + domain.encode() + b">"
    
    # Ensure total length <= 512 (including CRLF)
    # SOML command: command + SP + FROM: + reverse_path + CRLF
    # command = 4, SP = 1, FROM: = 5, CRLF = 2 => 12 constant overhead
    max_reverse_path_len = 512 - 12
    if len(reverse_path) > max_reverse_path_len:
        # Truncate path to fit (should not happen with our choices)
        reverse_path = reverse_path[:max_reverse_path_len]
    
    return b"SOML FROM:" + reverse_path + b"\r\n"