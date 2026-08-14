import struct

def generate() -> bytes:
    # SMTP BDAT request: constants and variable values
    # Use a valid chunk-size (e.g., 0 for non-data exploration, or a small positive)
    # For state exploration, pick a typical boundary value like 0 or 1
    chunk_size = 0  # Smallest valid, avoids large data overhead
    # last-marker is optional; include it to test both forms (here we omit for simplicity)
    # But we must satisfy the complete type-rule combination: the type rule says "BDAT"
    # and the IR says last-marker is optional. For valid requests, we can omit it.
    # However, note that the IR says "ABNF optional group; present as the literal bytes
    # ' LAST' on the final chunk, otherwise absent." Since we are not sending data,
    # we can omit. But to explore state, we might include it. Let's include it for variety.
    include_last = True  # Toggle to explore state

    # Build the command line
    command = b"BDAT"
    sp = b" "
    chunk_size_bytes = str(chunk_size).encode('ascii')
    if include_last:
        last = b" LAST"
    else:
        last = b""
    crlf = b"\r\n"

    # Assemble in IR order: command, SP, chunk-size, last-marker, CRLF
    request = command + sp + chunk_size_bytes + last + crlf

    # Note: The chunk data length must equal chunk_size; if chunk_size > 0, we need exactly
    # that many bytes of data. Since we are only generating the command line (no data body),
    # we must handle the chunk data. Per RFC 3030, the BDAT command line is followed by
    # exactly chunk-size octets of data, then no further delimiter (the CRLF terminates the
    # command line, not the data). So for a complete BDAT request, we must include the data.
    # For chunk_size=0, no data follows. For chunk_size>0, we need to generate that many bytes.
    # To keep it valid and simple, we choose chunk_size=0 (no data) and optionally include LAST.
    # But if chunk_size>0, we must append data. Let's handle both: if chunk_size>0, generate
    # dummy data (e.g., 'x' repeated). For state exploration, we can use a small non-zero value.
    # However, the contract says "prefer SUT/config/captured-message values" but we have none.
    # So we'll use chunk_size=0 and include LAST to have a valid final chunk.
    # But the IR says chunk-size is "1*DIGIT", so 0 is allowed (per RFC 3030, 0 is valid).
    # And last-marker only appears on the final chunk. So chunk_size=0 with LAST is valid.
    # However, if we include LAST, it implies final chunk, which is fine.
    # If we wanted to explore non-final chunk, we would omit LAST and set chunk_size>0.
    # For a single request, we can choose either. Let's generate a non-final chunk (no LAST)
    # with small data to exercise data path. But then we must include data. That's okay.
    # Let's change to chunk_size=1, omit LAST, and include 1 byte of data.
    # This yields a valid BDAT request that is not final, suitable for state exploration.
    # But the contract says "return exactly one complete BDAT request". A BDAT request with
    # chunk_size=1 and no LAST is complete (non-final). Valid.
    # So we'll rebuild:
    chunk_size = 1
    include_last = False
    chunk_size_bytes = str(chunk_size).encode('ascii')
    request = command + sp + chunk_size_bytes + (b" LAST" if include_last else b"") + crlf
    # Add data: exactly chunk_size bytes
    # Use a printable ASCII character for clarity
    data = b"X"  # single byte
    request += data

    # Verify length: chunk_size must match data length
    # (We already know it does)
    return request