import random

def generate() -> bytes:
    # Build the SAML request according to RFC 5321.
    # Fields in IR order: command, space, from_keyword, reverse_path, crlf.
    command = b"SAML"
    space = b" "
    from_keyword = b"FROM:"
    # Vary the reverse-path to reach unobserved legal transitions.
    # Use a null reverse-path (i.e., "<>") or a valid mailbox to enable different SUT behaviors.
    reverse_path = random.choice([b"<>", b"<user@example.com>", b"<postmaster@test.org>", b"<@relay1.com,@relay2.net:user@dest.org>"])
    crlf = b"\r\n"
    return command + space + from_keyword + reverse_path + crlf