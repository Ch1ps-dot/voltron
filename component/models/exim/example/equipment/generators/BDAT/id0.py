def generate() -> bytes:
    command_verb = b"BDAT"
    space_after_command = b" "
    size = b"0"
    last_parameter = b" LAST"
    crlf = b"\r\n"
    return command_verb + space_after_command + size + last_parameter + crlf