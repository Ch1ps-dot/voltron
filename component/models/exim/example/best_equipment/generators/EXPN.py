def generate() -> bytes:
    # EXPN command: constant command, SP, variable string, CRLF
    # Max total line length 512 octets including CRLF.
    # command = "EXPN" (4 bytes), SP = " " (1), CRLF = "\r\n" (2) => 7 bytes fixed.
    # So variable string max = 512 - 7 = 505 bytes.
    # Vary the String field over valid ABNF Strings to exercise unobserved states.
    # Include a well-known mailbox name, ordinary list names, and a maximum-length
    # string (505 octets, making the command line exactly 512).
    _expn_candidates = ("users", "postmaster", "list", "all", "staff", "announce", "mailing-list", "a" * 505)
    _expn_idx = getattr(generate, "_expn_idx", 0)
    mailing_list = _expn_candidates[_expn_idx % len(_expn_candidates)]
    generate._expn_idx = _expn_idx + 1
    # Build the complete request
    request = b"EXPN " + mailing_list.encode("ascii") + b"\r\n"
    # Ensure length constraint (it will be fine since "users" is short)
    # But if needed, truncate to max 505 for string portion.
    # For safety, check length of string part.
    max_string_len = 505
    if len(mailing_list) > max_string_len:
        mailing_list = mailing_list[:max_string_len]
        request = b"EXPN " + mailing_list.encode("ascii") + b"\r\n"
    return request