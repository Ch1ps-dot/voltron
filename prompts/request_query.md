You are an expert in networking protocols and RFC analysis.

Your task:
Analyze the provided RFC document and extract all *request-type* protocol messages.

A “request message type” is any protocol message whose purpose is to:
- initiate an operation
- query state or request data
- begin negotiation or connection setup
- solicit information (e.g., Solicit, Discover, Query)
- send capability or configuration requests
- trigger a request–response interaction

These include any messages named or described as:
"Request", "Query", "Solicit", "Discover", "Open", "Init", "Capability-Request",
"Hello-Request", or any subtype/TLV that behaves as a request.

You MUST follow these rules:

1. Extract ONLY request-type messages.
2. For each request-type message, provide:
   - name: exact name as written in the RFC
   - section_number: exact RFC section where the message is normatively defined
   - purpose: brief description of what operation or information is being requested
3. If a message has multiple request subtypes (e.g., TLV-based), list each separately.
4. If no request-type messages exist, return an empty array.
5. Output MUST be a single JSON object, and NOTHING else.

Output schema:
{
  "doc_name": "<RFC number or document name>",
  "request_message_types": [
    {
      "name": "string",
      "section_number": "string",
      "purpose": "string"
    }
  ]
}

Now analyze the RFC text below and output the result strictly in JSON.
<RFC_TEXT>