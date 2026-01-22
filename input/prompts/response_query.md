You are an expert in networking protocols and RFC analysis.

Your task:
Analyzing the format related sections of {$rfc_num} document of the {$pro_name} protocol, extract the fields from the **response message** that can be used to distinguish or identify the message type or function. Briefly explain how each field is used for this purpose. Focus only on fields that directly determine the type of the response message, and do not include fields related to content, parameters, or other functionalities. Only return the most related field in json file. 

**Format related document sections:**
${rfc_doc}

**Output the result in the following JSON format:**


{
  "field_name": "",
  "position": "",
  "explanation": "",
  "value": []
}



**Sample output:**

{
  "field_name": "Status-Code",
  "position": "First element of the response line",
  "explanation": "Used to distinguish the result and type of HTTP response messages, such as 200, 404, 500, etc."
  "value": [200, 201, 204, 400, 401, 403, 404, 500, 501, 502, ...]
}


Please extract and explain only the fields related to **response messages**, strictly according to the format and requirements above.
Only respond with the analysis result in JSON format.
