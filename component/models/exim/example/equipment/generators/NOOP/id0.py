import struct

def generate() -> bytes:
    # verb: "NOOP" in ASCII (4 bytes, case-insensitive per RFC 5321 Section 2.4)
    verb = b"NOOP"
    
    # parameter: optional SP String; we choose a minimal valid parameter (SP + "test")
    # to exercise state exploration. Servers SHOULD ignore it per RFC 5321 Section 4.1.1.9.
    parameter = b" test"
    
    # crlf: required line terminator CR (0x0D) LF (0x0A) per RFC 5321 Sections 2.3.8 and 4.1.1.
    crlf = b"\r\n"
    
    # Assemble in IR order: verb, parameter, crlf
    return verb + parameter + crlf