import struct

def generate() -> bytes:
    # Build the SMTP SEND request according to RFC 5321
    # Fields in IR order: command, separator, from_keyword, reverse_path, line_ending
    
    # command: constant "SEND" (4 bytes, ASCII)
    command = b"SEND"
    
    # separator: constant " " (1 byte)
    separator = b" "
    
    # from_keyword: constant "FROM:" (5 bytes, ASCII)
    from_keyword = b"FROM:"
    
    # reverse_path: variable field, choose a valid valid path or null reverse-path
    # For state exploration, use a common valid mailbox: <postmaster@example.com>
    # Include angle brackets and ensure total line length <= 512 octets
    # Path max 256 octets, our chosen path is well within limits
    reverse_path = b"<postmaster@example.com>"  # use a valid path to reach unobserved legal transitions (e.g., 250 response after HELO)
    
    # line_ending: constant "\r\n" (2 bytes)
    line_ending = b"\r\n"
    
    # Assemble the full request
    request = command + separator + from_keyword + reverse_path + line_ending
    
    # Validate total length <= 512 octets (RFC 5321 limit)
    assert len(request) <= 512, "Request exceeds SMTP line length limit"
    
    return request