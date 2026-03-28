You are an expert in networking protocols and RFC analysis.

## Your task:
Analyzing the format related sections of {$rfc_num} document of the {$pro_name} protocol, extract ONLY the fields from the **response message** that are response codes / status codes / result codes (or their protocol-specific equivalents). These are the fields explicitly used to distinguish different response types (for example: Status-Code, Result-Code, Response-Code, numeric/textual outcome codes).

Focus only on code-like fields that directly identify response type. Do NOT include session IDs, sequence numbers, flags, transaction IDs, message names, or other payload fields. For each identified field, briefly explain how it is used to distinguish response types, and list the possible values if they are explicitly defined in the RFC. Only return the analysis result in a JSON array format as specified below, with one element per identified field.

- Output all relevant fields as elements in a JSON array. Put the most critical distinguishing fields first (e.g., Method before Subtype).
- The value array must be character strings, bytes, or numbers as explicitly defined in the RFC. Do NOT include inferred or example values that are not directly specified in the document.
- For string values in the `value` array, each item must contain only letters, digits, or underscores (`^[A-Za-z0-9_]+$`).

## **Format related document sections:**
${rfc_doc}

## **Output the result in the following JSON array format (required):**

[
  {
    "field_name": "",
    "position": "",
    "explanation": "",
    "value": []
  },
  ...
]

## **Sample output:**

[
  {
    "field_name": "Status-Code",
    "position": "First element of the response line",
    "explanation": "Numeric code indicating success, client error, server error, etc.",
    "value": [200, 201, 204, 300, 301, 302, 400, 401, 403, 404, 500, 502]
  },
  {
    "field_name": "Result-Code",
    "position": "Header or fixed field in response body",
    "explanation": "Protocol-specific result code used to indicate operation outcome; list protocol-defined values if present.",
    "value": []
  }
]

## **Output Constraint**

- Only include fields that are response/status/result codes or equivalent that directly distinguish response types.
- Do NOT include session identifiers, sequence/ack numbers, flags, message names, or other non-code fields.
- Output strictly a JSON array as specified above.