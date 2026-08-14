def generate() -> bytes:
    # IR order: verb (constant "HELP", 4 bytes), argument (optional, variable length), line-terminator (constant "\r\n", 2 bytes)
    verb = b"HELP"
    # Choose a valid argument: a simple string preceded by a space. Vary for exploration; here use common string "domain"
    argument = b" domain"
    line_terminator = b"\r\n"
    return verb + argument + line_terminator