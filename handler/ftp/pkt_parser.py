
def packet_parser(response_message):
    if isinstance(response_message, bytes):
        response_message = response_message.decode('utf-8', errors='ignore')
    
    if len(response_message) < 3 or not response_message[:3].isdigit():
        raise ValueError("Status code cannot be located or is not numeric")
    
    reply_code = int(response_message[:3])
    
    valid_values = [
        110, 120, 125, 150, 200, 202, 211, 212, 213, 214, 215, 
        220, 221, 225, 226, 227, 230, 250, 257, 331, 332, 350, 
        421, 425, 426, 450, 451, 452, 500, 501, 502, 503, 504, 
        530, 532, 550, 551, 552, 553
    ]
    
    if valid_values and reply_code not in valid_values:
        raise ValueError("Status code is not in the allowed set")
    
    return reply_code