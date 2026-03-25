You are an expert in networking protocols and RFC analysis.

## Your task:
Analyzing the format related sections of {$rfc_num} document of the {$pro_name} protocol, extract all fields from the **response message** that can be used to distinguish or identify the message type or function. This includes single fields (e.g., `Status-Code`) and combinations of multiple fields (for example when two or more header fields jointly determine the response category).

For cases where the response category is determined by a combination of fields, list the combined fields together as a single JSON element: set `field_name` to the comma-separated field names (e.g., `Type, Subtype`) and explain how their combination determines the response type. For each field or field-group, briefly explain how it is used to distinguish response types and list possible values if explicitly defined in the RFC.

Do NOT include fields that are purely content or parameters (payload), but include any structural or header fields that participate in determining response type (status/result codes, message-type identifiers, combined header keys used for discrimination).

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

## **Sample output (single and combined fields):**

[
  {
    "field_name": "Status-Code",
    "position": "First element of the response line",
    "explanation": "Numeric code indicating success, redirect, client error, server error; primary discriminator of response semantics.",
    "value": [200, 201, 204, 300, 301, 302, 400, 401, 403, 404, 500, 502]
  },
  {
    "field_name": "Type, Subtype",
    "position": "Header fields (Type header and Subtype header)",
    "explanation": "Some protocols require both `Type` and `Subtype` headers to identify precise response semantics; the pair (Type, Subtype) together maps to the response handling logic.",
    "value": []
  }
]

## **Output Constraint**

- Extract and explain all fields or field-groups that determine response message type, including multi-field combinations.
- Do NOT include purely payload/content fields or unrelated state identifiers.
- Output strictly a JSON array as specified above; each element must describe one field or one combined field-group.