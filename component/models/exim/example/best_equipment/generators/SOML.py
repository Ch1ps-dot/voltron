def generate() -> bytes:
    candidates = (
        b'SOML FROM:<postmaster@example.com>\r\n',
        b'SOML FROM:<user@example.com>\r\n',
        b'SOML FROM:<>\r\n',
    )
    generate._n = (getattr(generate, "_n", -1) + 1) % len(candidates)
    return candidates[generate._n]