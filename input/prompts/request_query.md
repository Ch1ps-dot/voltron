You are an expert in networking protocols and RFC analysis.

## Your task:
Analyzing the format related sections of ${rfc_num} document of the ${pro_name} protocol, extract ALL fields from the **request message** that can be used to distinguish or identify the message type or function. For each field, briefly explain how it is used for this purpose. Focus only on fields that directly determine the type of the request message, and do not include fields related to content, parameters, or other functionalities.

- Output all relevant fields as elements in a JSON array.

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