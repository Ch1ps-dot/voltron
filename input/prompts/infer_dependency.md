
You are an expert in **network protocol analysis, request sequence dependency reasoning, and request-response validity verification**.

Your task has two core objectives:
1.  First, **infer the dependency relationship between the last sent request message and the current sent request message** based on the protocol specification.
2.  Then, based on this dependency relationship and the protocol state, **determine which response message types are legal to be received next for the current request**.

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

1. **Step 1: Infer the dependency relationship between two requests**
   Analyze the relationship between `$last_request` and `$current_request` according to `$rfc_content`, and classify it into one of the following categories:
   - **dependent**: The `$current_request` can be sent after `$last_request` **only if** specific protocol states or preconditions are met (e.g., a "file exists" response to a `STAT` request is required before sending a `RETR` request).
   - **Independent**: The `$current_request` has no dependency on `$last_request` and can be sent at any time.

2. **Step 2: Determine valid next response types**
   Based on the inferred dependency relationship and the protocol specification, evaluate which candidate response types are legal for the `$current_request`.
   - Treat the tuple `($last_request, $current_request, dependency_relationship)` as a **distinct observable protocol state**.
   - The validity of the response must be constrained by both the request sequence dependency and the protocol's request-response mapping rules.

---

### **Inference Rules**

#### **Rule 1: Dependency Relationship Inference**

- The relationship must be inferred **only from the provided `$rfc_content`**, with no assumptions about implementation-specific behavior.
- If the specification does not explicitly define the relationship between the two requests, classify it as **Independent**.

#### **Rule 2: Valid Response Determination**

A candidate response type is considered valid if and only if **both** of the following conditions are met:
1. **Request sequence validity**: The `$last_request → $current_request` sequence complies with the inferred dependency relationship (invalid sequences directly result in an empty valid response list).
2. **Protocol request-response validity**:
   - The RFC explicitly defines the response as a legal outcome for the `$current_request` in the current protocol state, **or**
   - The RFC does not specify any preconditions that are violated by the `$last_request → $current_request` sequence.

A candidate response type **must be excluded** if any of the following is true:
- The `$last_request → $current_request` sequence is **Invalid** (violates protocol dependency rules).
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
  1. `request_dependency`: The dependency relationship between `$last_request` and `$current_request` (value must be one of: `dependent`, `independent`).
  2. `next_response`: A list of allowed next response message types (empty list if no valid responses).

---

### **Output Format Example**

#### Example 1: Mandatory sequential dependency with valid responses

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
2. The `request_dependency` value is exactly one of the two predefined categories.
3. The `next_response` list contains **only** elements from the provided `$response_types`.
4. No responses requiring unsatisfied preconditions are included in `next_response`.
5. No server-specific or implementation-specific behavior is assumed.
6. The tuple `($last_request, $current_request, dependency_relationship)` is treated as a distinct protocol state.

