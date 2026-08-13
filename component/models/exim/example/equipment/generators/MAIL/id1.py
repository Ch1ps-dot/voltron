def generate() -> bytes:
    command_verb = b"MAIL"
    sp = b" "
    from_arg = b"FROM:"
    reverse_path = b"<>"
    crlf = b"\r\n"
    return command_verb + sp + from_arg + reverse_path + crlf