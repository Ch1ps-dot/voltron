_candidates = [
    b"SAML FROM:<user@example.com>\r\n",
    b"SAML FROM:<>\r\n",
    b"SAML FROM:<a@b>\r\n",
    b"SAML FROM:<user@[127.0.0.1]>\r\n",
    b"SAML FROM:<User@example.com>\r\n",
    b"SAML FROM:<" + b"a" * 64 + b"@" + b"b" * 63 + b"." + b"c" * 63 + b"." + b"d" * 61 + b">\r\n",
]
_index = 0

def generate() -> bytes:
    global _index
    request = _candidates[_index]
    _index = (_index + 1) % len(_candidates)
    return request