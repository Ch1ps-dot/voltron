You are an expert in networking protocols and RFC analysis.

## Your task:
Analyzing the format related sections of {$rfc_num} document of the {$pro_name} protocol, extract ONLY the fields from the **request message** that are method codes / request codes / function codes (or their protocol-specific equivalents). These are the fields explicitly used to distinguish different request types or subtypes (for example: Method, Request-Type, Subtype, numeric/textual operation codes).

Focus only on code-like fields that directly identify request type. Do NOT include session IDs, sequence numbers, flags, transaction IDs, message names, or other state/payload fields. For each identified field, briefly explain how it is used to distinguish response types, and list the possible values if they are explicitly defined in the RFC. Only return the analysis result in a JSON array format as specified below, with one element per identified field.

- Output all relevant fields as elements in a JSON array. Put the most critical distinguishing fields first (e.g., Method before Subtype).
- The value array must be character strings, bytes, or numbers as explicitly defined in the RFC. Do NOT include inferred or example values that are not directly specified in the document.
- For string values in the `value` array, each item must contain only letters, digits, or underscores (`^[A-Za-z0-9_]+$`).

## **Format related document sections:**
{$rfc_doc}

## **Sample output:**

[
  {
    "field_name": "Method",
    "position": "First element of the request line",
    "explanation": "Used to distinguish the operation type of HTTP requests, such as GET, POST, PUT, etc.",
    "value": ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
  },
  {
    "field_name": "Request-Type, Subtype",
    "position": "Header fields or first line tokens (combined)",
    "explanation": "Some protocols require both a Request-Type and a Subtype header to identify the exact operation; together they determine request handling.",
    "value": []
  }
]

## **Output Constraint**

- Please extract and explain only the fields related to **request messages** that determine message type or function, strictly according to the format and requirements above.
- Only respond with a JSON array as specified.