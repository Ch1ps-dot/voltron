def generate() -> bytes:
    command_verb = b"BDAT"
    space_after_command = b" "
    size = b"1024"
    last_parameter = b""
    crlf = b"\r\n"
    return command_verb + space_after_command + size + last_parameter + crlf