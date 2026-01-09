def packet_parser(response, allowed_values=None):
    """
    Parse an FTP-style reply and extract the 3-digit status/reply code as integer.

    Parameters:
    - response: str or bytes containing the protocol response message.
    - allowed_values: optional iterable of allowed reply codes (ints or strings). If provided and non-empty,
                      the extracted code will be validated against it.

    Returns:
    - int: the extracted 3-digit reply code.

    Raises ValueError if the code cannot be located, is not numeric, or not in allowed_values (when supplied).
    """
    if isinstance(response, bytes):
        try:
            text = response.decode('ascii', errors='replace')
        except Exception:
            text = response.decode('latin-1', errors='replace')
    elif isinstance(response, str):
        text = response
    else:
        raise ValueError("response must be bytes or str")

    # Split into lines; this handles CRLF and LF uniformly
    lines = text.splitlines()

    # Search for a line that begins with exactly three digits followed by space or hyphen.
    for line in lines:
        if len(line) < 3:
            continue
        # Consider only the start of the line as per specification
        prefix = line[:3]
        if all(ch.isdigit() for ch in prefix):
            # If there's a fourth character, it should be a space or hyphen per format;
            # however some implementations may not include more text, so accept if line is exactly 3 chars too.
            if len(line) == 3 or (len(line) >= 4 and line[3] in (' ', '-')):
                # We have a candidate
                try:
                    code_int = int(prefix)
                except Exception:
                    raise ValueError("Extracted status code is not numeric")
                # If allowed_values provided and non-empty, validate membership
                if allowed_values:
                    # Normalize allowed values to integers where possible
                    allowed_set = set()
                    for v in allowed_values:
                        try:
                            allowed_set.add(int(v))
                        except Exception:
                            # skip values that cannot be interpreted as integers
                            continue
                    if allowed_set and code_int not in allowed_set:
                        raise ValueError("Extracted status code not in allowed set")
                return code_int

    # If not found in any line, raise error
    raise ValueError("Status code cannot be located")