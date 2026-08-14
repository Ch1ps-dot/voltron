def generate() -> bytes:
    # RSET command verb in canonical uppercase (case-insensitive per RFC 5321)
    command_verb = b"RSET"
    # No arguments or SP after RSET, per RFC 5321 Section 4.1.1
    # Line terminator: CR (0x0D) followed by LF (0x0A)
    crlf = b"\r\n"
    # Assemble the complete RSET request
    return command_verb + crlf