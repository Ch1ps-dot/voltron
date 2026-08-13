def generate() -> bytes:
    # EXPN command: constant command, SP, variable string, CRLF
    # Max total line length 512 octets including CRLF.
    # command = "EXPN" (4 bytes), SP = " " (1), CRLF = "\r\n" (2) => 7 bytes fixed.
    # So variable string max = 512 - 7 = 505 bytes.
    # Vary the String field over valid ABNF Strings to exercise unobserved states.
    # Include a well-known mailbox name, ordinary list names, and a maximum-length
    # string (505 octets, making the command line exactly 512).
    _expn_candidates = (
        'Example-People',
        'example-people',
        'Example_People',
        'users',
        'postmaster',
        'list',
        'all',
        'staff',
        'announce',
        'mailing-list',
        'users@example.com',
        'postmaster@example.com',
        'list@[127.0.0.1]',
        'a' * 505,
        'a' * 504 + '!',
        '!' * 505,
    )
    _expn_idx = getattr(generate, '_expn_idx', 0)
    mailing_list = _expn_candidates[_expn_idx % len(_expn_candidates)]
    generate._expn_idx = _expn_idx + 1
    # Build the complete request
    request = b'EXPN ' + mailing_list.encode('ascii') + b'\r\n'
    # The String field is limited to 505 octets, so the whole command line
    # stays at or below the protocol maximum of 512 octets including CRLF.
    max_string_len = 505
    if len(mailing_list) > max_string_len:
        mailing_list = mailing_list[:max_string_len]
        request = b'EXPN ' + mailing_list.encode('ascii') + b'\r\n'
    return request