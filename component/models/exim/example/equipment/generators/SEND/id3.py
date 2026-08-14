import struct
import random

def generate() -> bytes:
    # Build the SMTP SEND request according to RFC 5321
    # Fields in IR order: command, separator, from_keyword, reverse_path, line_ending
    
    # command: constant "SEND" (4 bytes, ASCII)
    command = b"SEND"
    
    # separator: constant " " (1 byte)
    separator = b" "
    
    # from_keyword: constant "FROM:" (5 bytes, ASCII)
    from_keyword = b"FROM:"
    
    # reverse_path: variable field, choose a valid path or null reverse-path
    # For state exploration, vary the reverse-path value to reach unobserved legal transitions.
    # Use a common legal mailbox or null reverse-path to explore different SUT states.
    # SMTP allows Path (<@domain1,@domain2:mailbox>) or null reverse-path (<>).
    # We vary among these to increase coverage of legal transitions.
    reverse_path = random.choice([
        b"<postmaster@example.com>",
        b"<>",
        b"<user@example.org>",
        b"<@relay1.example.com,@relay2.example.net:user@dest.org>"
    ])
    
    # line_ending: constant "\r\n" (2 bytes)
    line_ending = b"\r\n"
    
    # Assemble the full request
    request = command + separator + from_keyword + reverse_path + line_ending
    
    # Validate total length <= 512 octets (RFC 5321 limit)
    assert len(request) <= 512, "Request exceeds SMTP line length limit"
    
    return request