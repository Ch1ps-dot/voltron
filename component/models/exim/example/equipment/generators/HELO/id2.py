def generate() -> bytes:
    # Make HELO generate additional interesting domains to reach states not yet seen
    # The base generator only used short, common domains; RFC 5321 allows any domain, including long ones
    # and IP-literal forms. Include a domain at the 255-octet domain-name limit.
    domains = [
        "example.com",
        "mail.example.org",
        "localhost",
        "[127.0.0.1]",
        "very.long.domain.name.that.is.still.under.512.octets.total.example.com",
        "[IPv6:2001:db8::1]",
        "UPPER.CASE.EXAMPLE.COM",
        "label-with-hyphens.example.com",
        "xn--bcher-kva.example",
        ".".join([
            "a" * 63,
            "b" * 63,
            "c" * 63,
            "d" * 63,
        ]),
    ]
    i = getattr(generate, "_idx", 0)
    domain = domains[i % len(domains)]
    generate._idx = i + 1
    return b"HELO " + domain.encode("ascii") + b"\r\n"
