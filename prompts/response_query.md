You are an expert in networking protocols and RFC analysis.

Your task:
Analyzing the $rfc_number document of the $pro_name protocol, identify and summarize all categories of response-type protocol messages defined in the RFC.
A “response message type” is any protocol message whose purpose is to reply to a request, acknowledge an action, return data, confirm state, provide a status report, or otherwise serve as the *response* side of a request/response interaction.

You MUST follow these rules:

1. For each message provide:
   - name: Exact message name as written in the RFC
   - section_number: Exact RFC section number where the message type is defined (e.g., “3.1.2”)

2. If the RFC contains no response messages, return an empty array.

3. Output MUST be a single JSON object and nothing else.

JSON output schema:

```json
{
  "doc_name": "<RFC number or document name>",
  "response_message_types": [
     {
       "name": "string",
       "section_number": "string"
     }
  ]
}
```

Now analyze the RFC document and output the result strictly in JSON.
