import hashlib
import re

def packet_observer(response: bytes) -> str:
    if not isinstance(response, bytes):
        response = b""
    try:
        text = response.decode("ascii", errors="replace")
    except Exception:
        text = response.decode("ascii", errors="replace")
    
    # Split into lines (SMTP lines are CRLF terminated)
    lines = text.split("\r\n")
    normalized_lines = []
    
    for line in lines:
        if not line:
            normalized_lines.append("")
            continue
        
        # Extract the SMTP reply code (first three digits)
        reply_code_match = re.match(r"(\d{3})", line)
        if not reply_code_match:
            normalized_lines.append(line)
            continue
        
        reply_code = reply_code_match.group(1)
        rest = line[3:]  # rest after the reply code
        
        # Check if there is a space separator (indicating text follows)
        if rest.startswith(" "):
            separator = " "
            text_part = rest[1:]  # after the space
        else:
            separator = ""
            text_part = rest
        
        # Check if the text part starts with an enhanced status code
        # Format: x.y.z where x, y, z are digits
        enhanced_match = re.match(r"(\d+\.\d+\.\d+)", text_part)
        if enhanced_match:
            enhanced_code = enhanced_match.group(1)
            remaining_text = text_part[len(enhanced_code):]
            # Normalize the enhanced status code: replace each digit component with a marker
            # We preserve the dotted structure but replace exact digits with placeholders
            enhanced_parts = enhanced_code.split(".")
            normalized_enhanced = ".".join("X" if part.isdigit() else part for part in enhanced_parts)
            # Replace the enhanced code with normalized version
            normalized_line = reply_code + separator + normalized_enhanced + remaining_text
        else:
            # No enhanced code; keep the line as is but normalize any dynamic fields beyond the reply code
            # The protocol only identifies reply code and enhanced status code as fields with controlled values
            # For normal text, we preserve it as-is (non-dynamic content)
            normalized_line = reply_code + separator + text_part
        
        normalized_lines.append(normalized_line)
    
    normalized_text = "\r\n".join(normalized_lines)
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()