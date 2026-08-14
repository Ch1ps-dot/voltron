def generate() -> bytes:
    # Build the SAML request according to RFC 5321.
    # Fields in IR order: command, space, from_keyword, reverse_path, crlf.
    command = b"SAML"
    space = b" "
    from_keyword = b"FROM:"
    # Choose a valid reverse-path with angle brackets and optional source route.
    # Use a simple local-part@domain format (max 256 octets).
    reverse_path = b"<sender@example.org>"
    # Ensure length constraint: variable length but must be <= 256.
    # Our chosen value is 22 bytes, well within limits.
    crlf = b"\r\n"
    return command + space + from_keyword + reverse_path + crlf