def generate() -> bytes:
    if not hasattr(generate, "_i"):
        generate._i = 0
        generate._vals = (b"postmaster", b"Example-People", b"a", b"x" * 505)
    arg = generate._vals[generate._i]
    generate._i = (generate._i + 1) % len(generate._vals)
    return b"EXPN " + arg + b"\r\n"