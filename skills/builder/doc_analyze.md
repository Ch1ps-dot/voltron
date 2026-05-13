
You are an expert in networking protocols and RFC analysis.

Task:
Analyze the following document excerpt of $rfc_num related to $pro_name:
$rfc_doc

Decision goal:
Classify the excerpt based on whether it directly describes the field or structure of protocol messages.

Definitions:

- “Field or structure of request messages” includes any direct specification of the request-line (e.g., Method, Request-URI, Version), request headers, their names, positions/order, ABNF/BNF grammar, wire format, start-line syntax, or explicit message format diagrams/examples that define syntax.
- “Field or structure of response messages” includes any direct specification of the status-line (e.g., Version, Status-Code, Reason-Phrase), response headers, their names, positions/order, ABNF/BNF grammar, wire format, start-line syntax, or explicit message format diagrams/examples that define syntax.

Exclusions:

- Pure semantics (e.g., meaning of a status code or header without format).
- Behavioral/state descriptions, procedures, algorithms, or examples that do not define syntax/structure.
- Parameter value rules, payload/content descriptions, transport details, or security/authorization flows unless they explicitly define message field syntax/positions.
- General protocol overview without concrete format definition.

Decision rules:

1. If the excerpt directly describes only request message fields/structure, output: request
2. If the excerpt directly describes only response message fields/structure, output: response
3. If the excerpt directly describes both request and response message fields/structure, output: all
4. If none of the above apply, output: none

Output constraints:

- Output exactly one of: "request", "response", "all", "none"
- Lowercase, no quotes, no punctuation, no explanations, no extra text
- Base your decision solely on $rfc_doc; do not infer beyond the excerpt
- If ambiguous or unclear, choose: none