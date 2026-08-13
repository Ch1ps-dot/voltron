_recipients = (
    b"user@example.com",
    b"postmaster@example.com",
    b"alice@example.org",
)
_counter = 0

def generate() -> bytes:
    global _counter
    mailbox = _recipients[_counter % len(_recipients)]
    _counter += 1
    return b"RCPT TO:<" + mailbox + b">\r\n"