def packet_parser(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        return ''
    try:
        text = data.decode('ascii', errors='replace')
    except Exception:
        return ''
    lines = text.splitlines()
    for line in lines:
        if len(line) >= 4:
            prefix = line[:3]
            if prefix.isdigit() and (line[3] == ' ' or line[3] == '-'):
                return prefix
    return ''