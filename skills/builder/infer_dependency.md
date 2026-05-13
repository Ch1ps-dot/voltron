You are an expert in **network protocol analysis, request sequence dependency reasoning, and request-response validity verification**.

Your task has two core objectives:
1.  First, **infer whether there is a semantic dependency relationship between the last sent request message and the current sent request message** based on the protocol specification. A semantic dependency means the outcome or validity of sending the current request is affected by whether the last request was sent (e.g., the current request is only allowed, or only meaningful, after the last request has been sent).
2.  Then, based on this semantic dependency relationship and the protocol state, **determine which response message types are legal to be received next for the current request**.

All reasoning must strictly comply with the provided protocol specification.

---

### **Input**

You will be given:
* **Protocol name**: $pro_name
* **Last sent request message type**: $last_request
* **Current sent request message type**: $current_request
* **Candidate response message types**: $response_types
* **Related content of specification document**: $rfc_content

---

### **Task Definition**

1. **Step 1: Infer the semantic dependency relationship between two requests**
   Analyze whether there is a **semantic dependency** between `$last_request` and `$current_request` according to `$rfc_content`, and classify it into one of the following categories:
   - **dependent**: Sending the `$last_request` affects the validity, meaning, or allowedness of sending the `$current_request`. The current request may only be allowed, or may only produce a meaningful response, after the last request has been sent.
   - **independent**: Sending the `$last_request` does not affect the validity, meaning, or allowedness of sending the `$current_request`. The current request can be sent at any time, with or without the last request, and the outcome is unchanged.

2. **Step 2: Determine valid next response types**
   Based on the inferred semantic dependency relationship and the protocol specification, evaluate which candidate response types are legal for the `$current_request`.
   - Treat the tuple `($last_request, $current_request, request_dependency)` as a **distinct observable protocol state**.
   - The validity of the response must be constrained by both the semantic dependency and the protocol's request-response mapping rules.

---

### **Inference Rules**

#### **Rule 1: Semantic Dependency Relationship Inference**
- The relationship must be inferred **only from the provided `$rfc_content`**, with no assumptions about implementation-specific behavior.
- A "semantic dependency" exists if the RFC states that:
  - The `$current_request` is only allowed after the `$last_request`; OR
  - The `$current_request` requires a state or information established by the `$last_request`; OR
  - The meaning or validity of the `$current_request` depends on the `$last_request` having been sent.
- If the specification does not indicate any such effect, classify the relationship as **independent**.

#### **Rule 2: Valid Response Determination**
A candidate response type is considered valid if and only if **both** of the following conditions are met:
1. **Request sequence validity**: The `$last_request → $current_request` sequence complies with the inferred semantic dependency relationship (invalid sequences directly result in an empty valid response list).
2. **Protocol request-response validity**:
   - The RFC explicitly defines the response as a legal outcome for the `$current_request` in the current protocol state, **or**
   - The RFC does not specify any preconditions that are violated by the `$last_request → $current_request` sequence.

A candidate response type **must be excluded** if any of the following is true:
- The `$last_request → $current_request` sequence is **Invalid** (violates the protocol's semantic dependency rules).
- The response requires a specific protocol state that is not satisfied by the request sequence.
- The response requires fulfillment of session-level conditions (e.g., authentication, session ID) or mandatory protocol phases that are not met by the request sequence.
- The validity of the response is ambiguous or conditional (no explicit RFC definition for the current state).

#### **General Rules**
- Do **NOT** assume server-specific or implementation-specific behavior.
- Do **NOT** invent response types that are not in the candidate list.

---

### **Selection Rules**
- Select valid responses **only from the provided `$response_types`**.
- If the request sequence is invalid or no candidate response meets the validity criteria, return an empty list.

---

### **Output Requirements**
* Output **only a single valid JSON object** (no explanations, comments, or additional text).
* The JSON object must contain **two mandatory keys**:
  1. `request_dependency`: The semantic dependency relationship between `$last_request` and `$current_request` (value must be one of: `dependent`, `independent`).
  2. `next_response`: A list of allowed next response message types (empty list if no valid responses).

---

### **Output Format Example**
#### Example 1: Semantic dependency with valid responses
{
  "request_dependency": "dependent",
  "next_response": ["200"]
}

#### Example 2: Independent requests with partial valid responses
{
  "request_dependency": "independent",
  "next_response": ["202", "400"]
}

---

### **Validation Checklist (for the model)**
Before finalizing the output, ensure:
1. The output is a valid JSON object with no syntax errors.
2. The `request_dependency` value is exactly one of the two predefined categories (reflecting semantic dependency).
3. The `next_response` list contains **only** elements from the provided `$response_types`.
4. No responses requiring unsatisfied preconditions are included in `next_response`.
5. No server-specific or implementation-specific behavior is assumed.
6. The tuple `($last_request, $current_request, request_dependency)` is treated as a distinct protocol state.

