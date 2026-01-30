
You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation for triggering server-side error responses and exceptional behaviors**.

Your task is to **regenerate Python code that mutates key protocol fields using randomized and boundary-covering values**, with the explicit goal of **eliciting protocol-defined error responses or abnormal server behaviors (e.g., 4xx/5xx responses, protocol error codes, or unexpected state transitions)** from the Server Under Test (SUT).

---

### **Input**

You will be given:

* **Protocol name**: `$pro_name`
* **Message type / message name**: `$msg_type`
* **Previous Generated Program**: `$code`
* **SUT (Server Under Test) Information**:
  `$info`

  The SUT information may include:

  * server/client configuration files
  * protocol feature flags
  * authentication or capability settings
  * known constraints inferred from prior executions

---

### **Your Task**

#### 1. Analyze the Previous Program and Protocol Structure

* Identify **key semantic fields** in the previous generated code (e.g., method names, identifiers, lengths, URIs, version numbers, authentication fields).
* Determine which fields:

  * directly influence protocol validation
  * are mapped to **specific error response codes or exceptional behaviors**
  * are sensitive to boundary values or malformed content

#### 2. Randomize and Mutate Key Fields with Boundary Coverage

* Modify the original program so that **critical fields are generated dynamically and randomly**, rather than using fixed constants.
* Randomization must **intentionally cover boundary and corner cases**, including but not limited to:

  * delete valid fields or add fictitious fields
  * convert the values of valid fields into garbled characters
  * empty, missing, or truncated fields
  * minimum, maximum, and off-by-one values for numeric or length-related fields
  * inconsistent cross-field relationships (e.g., mismatched length vs payload, invalid identifiers)
* The mutations should prioritize **triggering server-side error responses or abnormal behaviors**, rather than client-side exceptions.

#### 3. Error-Oriented Message Generation Strategy

* Prefer generating messages that are:

  * **semantically invalid according to the protocol specification**
  * **likely to reach deep server-side validation logic**
  * **capable of triggering standard error responses** (e.g., 4xx/5xx, protocol error codes, or unexpected state transitions)
* Keep the payload **compact and valid enough to be processed by the SUT**, but invalid in meaning.
* **Total serialized message length MUST be ≤ 1400 bytes** to ensure successful socket transmission.

#### 4. Generate a Python Function

* Produce a single Python function that:

  * constructs **one mutated, error-triggering `$msg_type` message**
  * uses **randomized values and boundary-covering mutations** for key fields
  * returns a `bytes` object
  * does **not raise exceptions during generation**

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, etc.)
* No third-party packages
* No input parameters
* Do NOT include networking code
* The function must be directly executable
* **CRITICAL**: The returned `bytes` object must have a total length **≤ 1400 bytes**

---

### **Function Prototype (Must Match Exactly)**

```python
def mutate_${msg_type}():
    """Generate one error-triggering $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes
    - Total message length ≤ 1400 bytes
    - Key fields are randomly generated with boundary coverage
    - Designed to elicit server-side error responses or abnormal behaviors
    """
    
    message = b''
    
    # Construct a semantically invalid, boundary-covering protocol message
    # using randomized critical fields to trigger error responses
    
    return message
```

---

### **Output Constraints**

* Output **only** the completed Python function code
* Do NOT include explanations, markdown, or text outside the function
* Do NOT include comments outside the function body

---
