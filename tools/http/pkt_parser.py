
def packet_parser(response_message):
    # Ensure response_message is in str format
    if isinstance(response_message, bytes):
        response_message = response_message.decode('utf-8')
    elif not isinstance(response_message, str):
        raise ValueError("Response message must be of type str or bytes.")
    
    # Extract the first line
    first_line = response_message.split('\n')[0]
    
    # Locate the status code in the first line before the space
    parts = first_line.split(' ', 2)
    
    # Check if the parts contain at least two elements
    if len(parts) < 2:
        raise ValueError("Status code cannot be located.")
    
    try:
        # Attempt to convert the status code part into an integer
        status_code = int(parts[1])
    except ValueError:
        raise ValueError("Extracted value is not numeric.")
    
    valid_values = list(range(100, 600)) # Valid range for HTTP status codes
    
    # Validate if status code is within the set of valid values
    if status_code not in valid_values:
        raise ValueError("Status code is not in the allowed set of values.")
    
    return status_code