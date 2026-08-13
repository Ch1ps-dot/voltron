def generate() -> bytes:
    candidates = (
        b'SOML FROM:<postmaster@example.com>\r\n',
        b'SOML FROM:<user@example.com>\r\n',
        b'SOML FROM:<>\r\n',
        b'SOML FROM:<a@b>\r\n',
        b'SOML FROM:<user@[127.0.0.1]>\r\n',
        b'SOML FROM:<User@example.com>\r\n',
        b'SOML FROM:<a@b.c>\r\n',
        b'SOML FROM:<local@domain>\r\n',
        b'SOML FROM:<' + b'a' * 64 + b'@' + b'b' * 63 + b'.' + b'c' * 63 + b'.' + b'd' * 61 + b'>\r\n',
    )
    generate._n = (getattr(generate, "_n", -1) + 1) % len(candidates)
    return candidates[generate._n]