import re

def packet_parser(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        return ''
    try:
        text = data.decode('ascii', errors='replace')
    except Exception:
        try:
            text = data.decode('latin-1', errors='replace')
        except Exception:
            return ''
    # Split into lines using CRLF/CR/LF
    lines = re.split(r'\r\n|\n|\r', text)
    if not lines:
        return ''
    # Search for a line beginning with a 3-digit code followed by space or hyphen
    first_match_index = None
    m_code = None
    for i, line in enumerate(lines):
        m = re.match(r'^\s*(\d{3})([- ])', line)
        if m:
            m_code = m.group(1)
            sep = m.group(2)
            first_match_index = i
            break
    if m_code is None:
        return ''
    if sep == ' ':
        return m_code
    # sep == '-' indicates multi-line reply; find terminator line that begins with same code + space
    terminator_re = re.compile(r'^\s*' + re.escape(m_code) + r' ')
    for line in lines[first_match_index+1:]:
        if terminator_re.match(line):
            return m_code
    # If terminator not found, cannot reliably locate status code per specification
    return ''