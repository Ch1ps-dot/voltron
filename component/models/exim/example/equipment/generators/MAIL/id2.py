import random

def generate() -> bytes:
    command_verb = b"MAIL"
    sp = b" "
    from_arg = b"FROM:"
    # Vary reverse-path to reach unobserved transitions: empty, typical, long, address-literal, mixed-case
    reverse_path = random.choice([
        b"<>",
        b"<user@example.com>",
        b"<a@b>",
        b"<user@[127.0.0.1]>",
        b"<User@example.com>",
        b"<" + b"a" * 64 + b"@" + b"b" * 63 + b"." + b"c" * 63 + b"." + b"d" * 61 + b">"
    ])
    # Optionally include AUTH parameter to reach AUTH-related states
    auth_param = b""
    if random.random() < 0.3:
        auth_param = b" AUTH=<>"
    crlf = b"\r\n"
    return command_verb + sp + from_arg + reverse_path + auth_param + crlf