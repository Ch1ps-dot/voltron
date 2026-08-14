def packet_checker(response: bytes) -> bool:
    if not isinstance(response, bytes):
        return False
    if len(response) < 5:
        return False

    # parse first line: reply-code (3 bytes) + separator (1 byte) + text-string (variable) + CRLF (2 bytes)
    # we need to handle multiline: each line ends with CRLF, last line ends with CRLF and no extra data

    # check for multiline: if first line after CRLF has more data, it's multiline
    # we enforce that the entire response consists of one or more lines of the same format
    # each line: 3 digits + optional space + text (may contain enhanced code) + CRLF

    pos = 0
    min_line_len = 5  # 3 digits + space + CRLF (or 3 digits + CRLF if no space? but spec says separator present only when text follows, so code-only would be 3 digits + CRLF = 5 bytes)
    # Actually spec: code-only: 3 digits + CRLF = 5 bytes
    # With text: 3 digits + space + text + CRLF => at least 6 bytes
    # But we need to handle both.

    while pos < len(response):
        if len(response) - pos < 5:
            return False
        # check first 3 bytes are digits
        for i in range(3):
            if not (48 <= response[pos + i] <= 57):
                return False
        reply_code = response[pos:pos+3].decode('ascii', errors='replace')
        # check if code is in primary field values
        # primary field values: ["220", "250", "458", "530"]
        # but we also need to check enhanced status code if present? The rule is empty, so use primary field.
        # However, we need to identify target from complete type-rule field combination.
        # Since TYPE_RULE_JSON is empty, we use primary field only.
        # So we must check that reply_code is one of the allowed values.
        if reply_code not in ["220", "250", "458", "530"]:
            return False

        # after the 3 digits, check separator
        # if next byte is space (0x20), then text follows
        # if next byte is CR (0x0D), then no text, just CRLF
        # anything else is invalid
        if response[pos + 3] == 0x20:
            # space present, text follows
            pos += 4
            # find CRLF
            crlf_idx = response.find(b'\r\n', pos)
            if crlf_idx == -1:
                return False
            # text is between pos and crlf_idx
            # check enhanced status code? The rule is empty, so we don't need to enforce enhanced code presence.
            # But we should check that the enhanced code, if present, matches allowed values? The field table says
            # enhanced status code is "dotted status code following the SMTP reply code in enhanced replies/DSNs"
            # and its value is ["5.7.0", "X.2.0", "X.2.1", "X.2.2", "X.3.5"].
            # Since the rule is empty, we can't use it; but the primary field is the reply code.
            # However, the task says: "Identify the target from the complete type-rule field combination; use the primary field only when the rule is unusable."
            # So we only use primary field (reply code). Enhanced status code is not enforced.
            # But we should still check that the text is printable ASCII or tab, no control chars?
            # Spec says text-string: 1*(%x09 / %x20-7E) — printable ASCII plus tab, no CRLF inside.
            for b in response[pos:crlf_idx]:
                if not (b == 0x09 or (0x20 <= b <= 0x7E)):
                    return False
            pos = crlf_idx + 2
        elif response[pos + 3] == 0x0D:
            # no space, check if next byte is LF
            if pos + 4 >= len(response) or response[pos + 4] != 0x0A:
                return False
            pos += 5
        else:
            return False

    # after processing all lines, we must have consumed exactly the whole response
    # (pos should equal len(response))
    if pos != len(response):
        return False

    # at least one line must be fully processed
    if pos == 0:
        return False

    return True