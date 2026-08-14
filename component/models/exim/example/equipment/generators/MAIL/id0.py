import random

def generate() -> bytes:
    # Build the MAIL request per RFC 5321
    # Fixed parts
    verb = b"MAIL"
    space = b" "
    from_keyword = b"FROM:"
    crlf = b"\r\n"
    
    # Choose a valid reverse-path (ReversePath)
    # Options: "<[A-d-l:]Mailbox>" or "<>"
    # For fuzzing we vary: empty (i.e., <>), simple mailbox, or with A-d-l
    choice = random.randint(0, 2)
    if choice == 0:
        reverse_path = b"<>"
    elif choice == 1:
        # Simple mailbox: local@domain
        local = random.choice([b"user", b"postmaster", b"test", b"admin"])
        domain = random.choice([b"example.com", b"test.org", b"mail.local"])
        reverse_path = b"<" + local + b"@" + domain + b">"
    else:
        # With A-d-l (source route): @domain1,@domain2:mailbox
        hop1 = random.choice([b"relay1.example.com", b"mx1.test.org"])
        hop2 = random.choice([b"relay2.example.net", b"mx2.local"])
        mailbox = random.choice([b"user@dest.org", b"postmaster@dest.com"])
        reverse_path = b"<@" + hop1 + b",@" + hop2 + b":" + mailbox + b">"
    
    # MailParameters (optional, can be empty or include one or more parameters)
    # Parameters: e.g., SIZE=12345, BODY=8BITMIME, etc.
    # For variability, sometimes include parameters, sometimes not
    if random.randint(0, 1) == 0:
        mail_parameters = b""
    else:
        # Choose a random parameter
        param_choice = random.randint(0, 2)
        if param_choice == 0:
            mail_parameters = b" SIZE=" + str(random.randint(1000, 100000)).encode()
        elif param_choice == 1:
            mail_parameters = b" BODY=8BITMIME"
        else:
            mail_parameters = b" BODY=7BIT"
    
    # Combine: verb + space + from_keyword + reverse_path + mail_parameters + crlf
    # Note: There is a space before mail_parameters only if parameters present
    if mail_parameters:
        # Ensure space before parameters (the spec says SP mail-parameter)
        # But we already have the space from from_keyword? Actually FROM: is directly followed by ReversePath, then space before parameters.
        # So we need a space between ReversePath and MailParameters if MailParameters is present.
        # So: FROM:<reverse_path> SP mail-parameter...
        request = verb + space + from_keyword + reverse_path + space + mail_parameters + crlf
    else:
        request = verb + space + from_keyword + reverse_path + crlf
    
    return request