def generate() -> bytes:
    import random
    mechanisms = [b"PLAIN", b"LOGIN", b"CRAM-MD5", b"XOAUTH2"]
    mechanism = random.choice(mechanisms)
    # For PLAIN, include an initial response; for others, omit it
    if mechanism == b"PLAIN":
        # valid base64-encoded initial response for PLAIN: \x00test\x00test
        initial_response = b" AHRlc3QAdGVzdA=="
    else:
        initial_response = b""
    return b"AUTH " + mechanism + initial_response + b"\r\n"