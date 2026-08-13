_EHLO_DOMAINS = (
    b"example.com",
    b"example.org",
    b"example.net",
    b"[127.0.0.1]",
    b"[IPv6:2001:db8::1]",
)
_ehlo_cursor = 0

def generate() -> bytes:
    global _ehlo_cursor
    domain = _EHLO_DOMAINS[_ehlo_cursor % len(_EHLO_DOMAINS)]
    _ehlo_cursor += 1
    return b"EHLO " + domain + b"\r\n"