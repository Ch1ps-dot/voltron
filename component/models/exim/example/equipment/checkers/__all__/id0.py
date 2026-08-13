def packet_checker(response: bytes) -> bool:
    # Must be bytes
    if not isinstance(response, bytes):
        return False
    
    # Must not be empty
    if not response:
        return False
    
    # Split into lines by CRLF
    lines = response.split(b'\r\n')
    # The last element after splitting will be empty if ending with CRLF, or incomplete if not
    # SMTP requires CRLF termination for each line, including the last
    if not response.endswith(b'\r\n'):
        return False
    # Remove trailing empty element from split
    if lines and lines[-1] == b'':
        lines = lines[:-1]
    else:
        # Did not end with CRLF properly
        return False
    
    if not lines:
        return False
    
    # Process each line as a reply line
    reply_code_str = None
    for line_idx, line in enumerate(lines):
        # Each line must be at least 3 bytes (digits) and can have separator and optional text
        if len(line) < 3:
            return False
        
        # First three bytes must be digits
        first_three = line[:3]
        try:
            code_str = first_three.decode('ascii')
        except UnicodeDecodeError:
            return False
        if not code_str.isdigit() or len(code_str) != 3:
            return False
        
        # Validate that the code is in the allowed list (primary field)
        allowed_codes = {b'220', b'221', b'250', b'252', b'354', b'503', b'530', b'550', b'554'}
        if first_three not in allowed_codes:
            return False
        
        # For the first line, record the reply code
        if reply_code_str is None:
            reply_code_str = code_str
        
        # Check the separator and optional text
        rest = line[3:]
        if rest:
            # First byte of rest must be separator (space or hyphen)
            sep = rest[0:1]
            if sep not in (b' ', b'-'):
                return False
            # If it's a hyphen, it's a continuation line (not final)
            if sep == b'-' and line_idx == len(lines) - 1:
                # Last line cannot have continuation separator
                return False
            # If it's a space, it's the final line (or a line with text)
            if sep == b' ' and line_idx != len(lines) - 1:
                # Non-final line cannot have space separator (must be hyphen)
                return False
            # The rest (after separator) must be printable ASCII (no control chars except CR/LF but those are already handled)
            text_part = rest[1:] if len(rest) > 1 else b''
            if text_part:
                # Must be printable ASCII (space through ~)
                for byte in text_part:
                    if byte < 0x20 or byte > 0x7e:
                        return False
        else:
            # No separator and no text: allowed only if this is the only line? Actually, RFC says code may be alone.
            # But if there is no separator, the line is just the code and CRLF.
            # This is allowed for any line, but if there are multiple lines, the separator must be present for continuation?
            # Actually, multi-line responses use the same code with hyphen, so if there is no text, it's still a valid line.
            # However, we must ensure that if there is no text, there is no separator, which is fine.
            pass
        
        # For enhanced status code: if the reply code is not exactly what we need for 5.7.0? Actually, the spec says
        # enhanced status code appears after the reply code. The rule is: if enhanced status code is present, it must be
        # 5.7.0. But we don't know if it's present. Since the primary field rule is empty, we only use primary field.
        # The task says: use primary field only when rule is unusable. Rule is empty, so use primary.
        # So we only check the reply code. The enhanced status code is not enforced because it's optional.
        # But we must ensure that if it appears, it conforms? Actually, the IR field table says the separator is optional,
        # and text is optional. The enhanced status code is part of the text. Since we don't have a rule, we don't enforce it.
        # However, we should ensure that the text (if present) does not contain any unexpected bytes.
        # We already check that text is printable ASCII.
        # Additionally, we could check for enhanced status code pattern if present, but not required.
        # According to the contract: "Identify the target from the complete type-rule field combination; use the primary field only when the rule is unusable."
        # So we just check the reply code.
        
    # If we reach here, all lines are valid. The entire response must be consumed (no trailing data).
    # We already checked that it ends with CRLF and split properly, so no trailing data.
    # However, we must ensure that the response is exactly the concatenation of lines with CRLF.
    # Our split already ensures that, but we need to verify that the reconstructed bytes match the original.
    # This is a sanity check: if there were extra bytes, split would not account for them.
    # Actually, our split already accounts for everything because we split on CRLF and the trailing empty string.
    # But to be safe, we can reconstruct and compare.
    reconstructed = b'\r\n'.join(lines) + b'\r\n'
    if reconstructed != response:
        return False
    
    return True