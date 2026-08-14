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
    choice = random.choice(["null", "simple", "with_at_domain", "with_at_domain_multi", "null_case", "local_underscore", "local_dotted", "local_quoted", "path_max_len", "path_minimal", "local_with_hyphen", "domain_with_hyphen"])
    
    if choice == "null":
        reverse_path = b"<>"
    elif choice == "simple":
        # Local-part (no special chars, <=64) and domain (simple)
        local = random.choice(["user", "test", "alice", "bob", "admin", "postmaster", "info", "mail", "contact", "support"])
        domain = random.choice(["example.com", "test.org", "mail.example", "example.net", "example.org", "test.com", "domain.com", "server.local"])
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    elif choice == "with_at_domain":
        # A-d-l: one or more "@" domain elements
        at_domain = b"@" + random.choice([b"relay1.com", b"mx1.test", b"gateway.org", b"smtp.example", b"mailrelay.net"])
        local = random.choice(["user", "test", "alice", "bob", "admin"])
        domain = random.choice(["example.com", "test.org", "example.net"])
        reverse_path = b"<" + at_domain + b":" + local.encode() + b"@" + domain.encode() + b">"
    elif choice == "with_at_domain_multi":
        # A-d-l with multiple hops
        at_domain1 = b"@" + random.choice([b"relay1.com", b"mx1.test", b"gateway.org"])
        at_domain2 = b"@" + random.choice([b"relay2.net", b"mx2.test", b"hop2.example"])
        local = random.choice(["user", "test", "alice", "bob"])
        domain = random.choice(["example.com", "test.org"])
        reverse_path = b"<" + at_domain1 + b"," + at_domain2 + b":" + local.encode() + b"@" + domain.encode() + b">"
    elif choice == "null_case":
        # null reverse-path with different representation (no spaces, just <>)
        reverse_path = b"<>"
    elif choice == "local_underscore":
        # local-part with underscore
        local = random.choice(["user_name", "test_user", "admin_user", "contact_person"])
        domain = random.choice(["example.com", "test.org", "mail.example"])
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    elif choice == "local_dotted":
        # local-part with dots (allowed)
        local = random.choice(["user.name", "first.last", "john.doe", "jane.smith", "a.b.c"])
        domain = random.choice(["example.com", "test.org", "mail.example"])
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    elif choice == "local_quoted":
        # local-part with quoted string (contains special characters)
        # Note: quoted local-parts are allowed per RFC 5321
        local = random.choice(["\"user name\"", "\"test\"", "\"a.b@c\"", "\"john;doe\""])
        domain = random.choice(["example.com", "test.org"])
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    elif choice == "path_max_len":
        # Generate a reverse-path that is near the maximum 256 octets
        # Use a long local-part and domain
        local = "a" * 64
        domain = "b" * 180 + ".com"
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
        # If exceeds 256, trim to fit
        if len(reverse_path) > 256:
            reverse_path = reverse_path[:256]
    elif choice == "path_minimal":
        # minimal valid reverse-path: just a single character local and domain
        local = "x"
        domain = "y"
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    elif choice == "local_with_hyphen":
        # local-part with hyphen
        local = random.choice(["user-name", "test-name", "alice-smith", "bob-jones"])
        domain = random.choice(["example.com", "test.org", "mail.example"])
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    else:  # domain_with_hyphen
        # domain with hyphens
        local = random.choice(["user", "test", "alice", "bob"])
        domain = random.choice(["my-domain.com", "test-domain.org", "mail-server.example", "sub-domain.example.com"])
        reverse_path = b"<" + local.encode() + b"@" + domain.encode() + b">"
    
    # Ensure total length <= 512 (including CRLF)
    # SOML command: command + SP + FROM: + reverse_path + CRLF
    # command = 4, SP = 1, FROM: = 5, CRLF = 2 => 12 constant overhead
    max_reverse_path_len = 512 - 12
    if len(reverse_path) > max_reverse_path_len:
        # Truncate path to fit
        reverse_path = reverse_path[:max_reverse_path_len]
    
    return b"SOML FROM:" + reverse_path + b"\r\n"