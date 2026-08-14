def packet_parser(response: bytes) -> bytes:
    try:
        text = response.decode("utf-8", errors="replace")
    except Exception:
        return b""

    # SMTP: first three characters of the first line are the reply code
    # Find the start of the first line
    first_line = text.split("\r\n")[0] if "\r\n" in text else text.split("\n")[0] if "\n" in text else text
    first_line = first_line.strip()
    if len(first_line) < 3:
        return b""
    code = first_line[:3]
    if not code.isdigit():
        return b""

    # Check if it's an enhanced reply (contains a space after the code then a dotted code)
    # Enhanced: "250 2.1.5 ..." or "250-2.1.5 ..."
    # We need to extract the enhanced status code only if present and valid
    # According to the field definitions, we look for the first three digits as SMTP reply code
    # and separately the enhanced status code (dotted). But the contract says return the primary field
    # or fixed primary-field tuple. The fields listed are separate: SMTP reply code and Enhanced status code.
    # The protocol is SMTP, the primary response-state field is the SMTP reply code.
    # The enhanced status code is an additional field. The contract says: "Return its canonical, stable,
    # protocol-defined value as UTF-8 bytes. Do not map it to an invented semantic label."
    # For SMTP, the canonical primary is the three-digit numeric code.
    # However, the RESPONSE_FIELDS_JSON also includes enhanced status code. But we are to use the JSON
    # to locate/decode the protocol's primary response-state field or fixed primary-field tuple.
    # The primary field is "SMTP reply code". So we return that.
    return code.encode("utf-8")