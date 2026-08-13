import random

def generate() -> bytes:
    # Build the HELP command line per RFC5321 and the IR field table.
    # Fields in order: command, argument, line_terminator.
    # command is constant "HELP" (uppercase ASCII).
    command = b"HELP"
    
    # argument: optional; if present, one SP followed by a printable ASCII string.
    # Choose uniformly between present and absent for state exploration.
    # Valid string: printable ASCII characters except CR (0x0D) and LF (0x0A).
    # Use a random length between 0 and 40 characters (0 means no argument).
    # To stay within 512 octets total, including verb and CRLF (2 bytes),
    # maximum argument length = 512 - len(command) - 1 (SP) - 2 (CRLF) = 512-6=506.
    # But random length up to 40 gives reasonable variety.
    if random.choice([True, False]):
        # Present argument with SP
        arg_len = random.randint(1, 40)
        # Generate printable ASCII excluding CR,LF (0x0D,0x0A). Range 0x20-0x7E except 0x0D,0x0A which are excluded.
        # Use bytes from 0x20 to 0x7E, but skip 0x0D (13) and 0x0A (10) - not in range.
        # Actually 0x20-0x7E includes only 0x0D,0x0A? No, they are below 0x20. So safe.
        # But also exclude 0x00-0x1F and 0x7F? "printable ASCII" typically 0x20-0x7E.
        # Let's generate from 0x20-0x7E (94 chars). No CR/LF in that range.
        argument = b" " + bytes(random.choice(range(0x20, 0x7F)) for _ in range(arg_len))
    else:
        # Absent argument: empty bytes
        argument = b""
    
    # line_terminator: constant CRLF (0x0D 0x0A)
    crlf = b"\r\n"
    
    # Assemble the complete request
    request = command + argument + crlf
    
    # Ensure total length <= 512 octets per RFC5321
    # If due to random generation it exceeds, truncate argument (but we set max 40, so safe).
    # Still, enforce safety:
    if len(request) > 512:
        # This shouldn't happen with our limits, but handle gracefully: reduce argument.
        # Remove argument and retry (or just clamp).
        # Simpler: ensure argument length doesn't exceed 505 (since command=4, crlf=2, max 512 => 506 for arg+SP, but actually SP is included in argument if present, so max 506 bytes for argument+SP).
        # We'll keep it simple: we know it's within 512.
        pass
    
    return request