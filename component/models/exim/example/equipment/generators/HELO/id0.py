def generate() -> bytes:
    domains = (
        "example.com",
        "mail.example.org",
        "localhost",
        "[127.0.0.1]",
    )
    i = getattr(generate, "_idx", 0)
    domain = domains[i % len(domains)]
    generate._idx = i + 1
    return b"HELO " + domain.encode("ascii") + b"\r\n"