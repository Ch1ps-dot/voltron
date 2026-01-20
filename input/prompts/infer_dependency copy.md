You are an expert in **network protocol analysis and request-response dependency reasoning**.

Your task is to **infer which response message types are legal to be received next**, given the **last received response message** and the **current sent request message**, based strictly on the provided protocol specification.

---

### **Input**

You will be given:
* **Protocol name**: $pro_name
* **Last received response message type**: $last_response
* **Current sent request message type**: $current_request
* **Candidate response message types**: $response_types
* **Related content of specification document**: $rfc_content

### **Task Definition**

For the combination of **the last received response message** and **the current sent request message**:
* Determine which response message types are **valid to be received next**
* The validity must be evaluated **conditioned on both the last response and current request**
* Treat the pair of last response + current request as representing a **distinct observable protocol state**

---

### **Inference Rules**

* A response is considered valid to be received next **for the current request (given the last response)** if:
  * The RFC explicitly defines it as a legal response to the current request in the state implied by the last response, **or**
  * The RFC does not specify any preconditions that are violated by the combination of the last response and current request
* If a valid response requires:
  * A specific prior protocol state (implied by the last response)
  * Fulfillment of session-level conditions (e.g., authentication, session ID)
  * Completion of a mandatory protocol phase
    and such conditions are **not satisfied by the last received response**, the response must be **excluded**
* If validity is ambiguous or conditional, **exclude the response**
* Do **NOT** assume server-specific or implementation-specific behavior

---

### **Selection Rules**

* Select **only** from the provided `Candidate response message types`
* Do **NOT** invent new response types

---

### **Output Requirements**

* Output **only a single valid JSON object**
* Do **NOT** include explanations, comments, or additional text
* The JSON object must map the key `next_response` to a list of **allowed next response message types**

---

### **Output Format Example**

{
  "next_response": ["200", "401", "503"]
}

---

### **Validation Checklist (for the model)**

Before finalizing the output, ensure:
* The output is valid JSON
* The key of the output is exactly `next_response`
* Every listed response appears in `Candidate response message types`
* No response requiring unsatisfied preconditions (from the last response) is included
* The combination of last response + current request is treated as a distinct protocol state
