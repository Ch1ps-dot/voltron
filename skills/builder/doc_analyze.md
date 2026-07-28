
You are an expert in networking protocols and RFC analysis.

Task:
Analyze the following document excerpt of $rfc_num related to $pro_name:
$rfc_doc

Decision goal:
Classify the excerpt based on whether it is related to request messages,
response messages, or both. A related section may describe message syntax,
fields, packet types, headers, properties, payloads, valid values, semantics,
state effects, processing rules, examples, or constraints that are useful for
constructing, parsing, validating, or reasoning about protocol messages.

Definitions:

- “Request-message related” includes any section that describes client-to-server
  messages, request packet types, request-line or command syntax, request
  headers/properties, request payloads, request fields and valid values,
  request examples, request preconditions, or rules for constructing,
  sending, validating, or processing a request.
- “Response-message related” includes any section that describes server-to-client
  messages, response packet types, status lines or status codes, response
  headers/properties, response payloads, response fields and valid values,
  response examples, error replies, acknowledgements, or rules for constructing,
  sending, validating, or processing a response.
- For protocols that do not explicitly use the words request and response,
  classify by direction and role: client-originated commands or packets are
  request-related; server-originated replies, acknowledgements, errors, or
  result packets are response-related.
- If a section describes a bidirectional packet type, a shared message format,
  common field encoding, common property encoding, or rules that apply to both
  request and response messages, classify it as all.

Exclusions:

- Transport details, deployment guidance, security considerations, IANA
  registries, terminology, motivation, and general protocol overviews, unless
  the excerpt connects them to specific request or response messages.
- Pure session behavior, algorithms, or state-machine prose that does not
  identify any request message, response message, packet type, field, property,
  status, error, payload, or message-processing rule.
- Historical notes, acknowledgements, references, conformance boilerplate, and
  editorial material.

Decision rules:

1. If the excerpt is related only to request messages, output request
2. If the excerpt is related only to response messages, output response
3. If the excerpt is related to both request and response messages, output all
4. If none of the above apply, output none

Output constraints (MANDATORY):

- The model MUST output exactly one and only one token from this set: request, response, all, none
- The output must be lowercase, with no quotes, no punctuation, no surrounding or trailing text or explanation
- Do NOT output anything other than the single chosen token above; any deviation is invalid
- Base your decision solely on $rfc_doc; do not infer beyond the excerpt
- If ambiguous or unclear, choose none
