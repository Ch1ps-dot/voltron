import base64
import random

def generate() -> bytes:
    # Step 1: Build the constant prefix "AUTH " (command + space)
    result = bytearray(b"AUTH ")
    
    # Step 2: Select a valid SASL mechanism name (1–20 characters from allowed set)
    # Allowed: ALPHA / DIGIT / '-' / '_'
    # Choose a common mechanism for state exploration: PLAIN, LOGIN, CRAM-MD5, DIGEST-MD5, etc.
    # We'll pick PLAIN as a common, valid mechanism.
    mechanism = b"PLAIN"
    result.extend(mechanism)
    
    # Step 3: Optionally add an initial response (space + base64string or "=")
    # For state exploration, vary presence: sometimes include, sometimes omit.
    # We'll include a valid base64-encoded "initial response" for PLAIN.
    # PLAIN initial response is: base64(\0username\0password)
    # We'll use a dummy username/password for fuzzing/state exploration.
    # To keep it valid, encode something simple.
    # For variety, we can randomize but keep within valid base64.
    # We'll include a space, then the base64 string.
    # For PLAIN, the initial response is optional; we'll include it.
    # The base64 string must not contain internal spaces; only trailing CRLF.
    # We'll generate a dummy authzid (empty) + authcid + passwd.
    # Example: \0user\0pass -> base64 -> AAd1c2VyAHBhc3M= (but careful with null bytes)
    # Actually, the base64 encoding of b'\x00user\x00pass' gives something like "AHVzZXIAcGFzcw==".
    # To be safe, we'll use a known valid value.
    # Let's use the string "AHVzZXIAcGFzcw==" which is base64 of \x00user\x00pass.
    # But we must ensure the base64 string is valid per RFC 4648, no padding issues.
    # Simpler: use "=" to denote empty initial response, which is valid.
    # For state exploration, we'll vary: sometimes "=", sometimes a base64.
    # We'll choose "=" for simplicity and to avoid length issues.
    # However, to be more realistic, we'll include a proper base64 response.
    # The initial response is optional; we can omit it entirely.
    # For variety, let's include it with a space and a base64 string.
    # We'll generate a random base64 string of length between 1 and 100 (but valid).
    # But to be deterministic and valid, we'll use a fixed base64 string.
    # Use "AHRlc3QAdGVzdA==" (base64 of \x00test\x00test).
    # That is a valid SASL PLAIN initial response.
    # We'll include it.
    result.extend(b" AHRlc3QAdGVzdA==")
    
    # Step 4: Terminate with CRLF
    result.extend(b"\r\n")
    
    # Ensure the entire line length does not exceed 512 octets (unless extension).
    # Our constructed line is short (< 512), so fine.
    return bytes(result)