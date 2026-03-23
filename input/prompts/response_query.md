You are an expert in networking protocols and RFC analysis.

## Your task:
Analyzing the format related sections of {$rfc_num} document of the {$pro_name} protocol, extract all fields from the **response message** that can be used to distinguish or identify the message type or function. Briefly explain how each field is used for this purpose. Focus only on fields that directly determine the type of the response message, and do not include fields related to content, parameters, or other functionalities.

- If the response message category is determined by a combination of multiple fields, consider the combined result as the identifying key, and describe these fields as a group (comma-separated) in one JSON element.
- Output all fields related to response type, each field or field group as a JSON element.

## **Format related document sections:**
${rfc_doc}

## **Output the result in the following JSON array format:**

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
    "explanation": "Used to distinguish the result and type of HTTP response messages, such as 200, 404, 500, etc.",
    "value": [200, 201, 204, 400, 401, 403, 404, 500, 501, 502, ...]
  },
  {
    "field_name": "Version",
    "position": "First and second element of the response line",
    "explanation": "The combination of Version and Status-Code can further distinguish protocol evolution and response type.",
    "value": ["HTTP/1.0", "HTTP/1.1", ...]
  }
]

## **Output Constraint**

- Please extract and explain all fields related to **response messages**, strictly according to the format and requirements above.
- Only output a JSON array, each element describes a field or field group.