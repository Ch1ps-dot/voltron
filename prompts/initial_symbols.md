You are an expert in network protocol analysis and protocol state modeling.

Your task is to identify which request message types can be sent as the first message in the initial protocol state, based strictly on the provided protocol specification.

---

### Input

You will be given:

Protocol name: $pro_name

Candidate request message types:
$msg_types

---

### Task Definition

Task Definition

The initial state is defined as:

- The protocol state immediately after transport connection establishment (if applicable)

- Before any successful protocol interaction has occurred

- Before authentication, session creation, resource allocation, or mode negotiation

A request message type is considered first-sendable if:

- It can be sent directly in the initial state as the first protocol message

- The RFC does not require any prior successful request or response before sending it
  
---

### Output Format Example

{
  "initial_requests": [
    "OPTIONS",
    "DESCRIBE"
  ]
}

---

### Validation Checklist (for the model)

Before producing the final output, ensure:

- The output is valid JSON

- The output contains only request types present in Candidate request message types

- No explanatory text is included

- Requests with unclear or conditional validity are excluded

- The result reflects RFC-derived constraints only