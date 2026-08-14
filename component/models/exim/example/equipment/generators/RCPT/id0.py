def generate() -> bytes:
    i = getattr(generate, "_i", 0)
    setattr(generate, "_i", i + 1)

    forward_paths = [
        "<user@example.com>",
        "<Postmaster>",
        "<@a.example,@b.example:user@example.com>",
        "<local@example.org>",
    ]

    rcpt_parameters = [
        "",
        " NOTIFY=SUCCESS,FAILURE",
        " ORCPT=rfc822;user@example.com",
        " NOTIFY=SUCCESS,FAILURE ORCPT=rfc822;user@example.com",
    ]

    path = forward_paths[i % len(forward_paths)]
    params = rcpt_parameters[(i // len(forward_paths)) % len(rcpt_parameters)]

    return ("RCPT TO:" + path + params + "\r\n").encode("ascii")