You are an expert in **network protocol analysis and request-response dependency reasoning**.

Your task is to **infer which request message types can be sent next**, given a specific request message and all of its possible response types, based strictly on the provided protocol specification.

---

### **Input**

You will be given:

* **Protocol name**: `$pro_name`
* **Current request message type**:

  ```
  $current_request
  ```
* **Possible response message types for the current request**:

  ```
  $response_types
  ```
* **Candidate request message types**:

  ```
  $request_types
  ```

---

### **Task Definition**

For **each response message type** resulting from the current request:

* Determine which request message types are **valid to be sent next**
* The validity must be evaluated **conditioned on that specific response**
* Treat each response as representing a **distinct observable protocol state**

---

### **Inference Rules**

* A request is considered valid to send next **after a given response** if:

  * The RFC explicitly allows it in the state implied by that response, **or**
  * The RFC does not specify any preconditions that are violated by that response
* If a request requires:

  * Authentication
  * A session identifier
  * Completion of a specific protocol phase
    and such conditions are **not satisfied by the given response**, the request must be **excluded**
* If validity is ambiguous or conditional, **exclude the request**
* Do **NOT** assume server-specific or implementation-specific behavior

---

### **Selection Rules**

* Select **only** from the provided `Candidate request message types`
* Do **NOT** invent new request types
* Evaluate each `(response → next request)` relation independently

---

### **Output Requirements**

* Output **only a single valid JSON object**
* Do **NOT** include explanations, comments, or additional text
* The JSON object must map **each response message type** to a list of **allowed next request message types**

---

### **Output Format Example**

```json
{
  "331": ["PASS"],
  "230": ["PWD", "CWD", "TYPE", "PASV", "QUIT"],
  "530": ["USER", "QUIT"]
}
```

---

### **Validation Checklist (for the model)**

Before finalizing the output, ensure:

* The output is valid JSON
* Every key corresponds to a response message type in `$response_types`
* Every listed request appears in `Candidate request message types`
* No request requiring unsatisfied preconditions is included
* Each response is treated as a distinct protocol state

---
