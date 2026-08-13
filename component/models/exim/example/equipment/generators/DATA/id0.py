def generate() -> bytes:
    # Per IR_FIELD_TABLE_JSON: command field is constant "DATA" (B), line-ending constant "\r\n" (B)
    # The serialization order is: command, then line-ending.
    # Both fields are of type "constant" with length "B" (byte string).
    # No variable fields, no derived lengths, no cross-field dependencies.
    # Return the complete DATA request as bytes.
    return b"DATA\r\n"