def generate() -> bytes:
    # EXPN command: constant command, SP, variable string, CRLF
    # Max total line length 512 octets including CRLF.
    # command = "EXPN" (4 bytes), SP = " " (1), CRLF = "\r\n" (2) => 7 bytes fixed.
    # So variable string max = 512 - 7 = 505 bytes.
    # Choose a valid mailing list name (common example, e.g., "users").
    # Use a common/valid list name string.
    mailing_list = "users"
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