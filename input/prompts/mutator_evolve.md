You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation for error response triggering**.

Your task is to **generate Python code that constructs a protocol message specifically designed to elicit error response messages (e.g., 4xx/5xx for SIP, standard error codes for other protocols) from the Server Under Test (SUT) or client** 

---

### **Input**

You will be given:

* **Protocol name**: $pro_name
* **Message type / message name**: $msg_type
* **Previous Generated Program**: $code
* **SUT (Server Under Test) Information**: 
   $info

   - The SUT information above may include:
    - configuration file of SUT
    - settings of client or server

---

### **Your Task**

1. **Analyze the previously generated code and protocol structure**
   - Identify syntactically valid but semantically non-compliant field values that strictly follow the protocol's defined error trigger conditions (e.g., missing user part in SIP URI → 484, invalid CSeq format → 400)
   - Pinpoint protocol fields that map directly to standard error response codes (no exploitation of unhandled exceptions or memory issues)
   - Calculate the maximum safe message length for socket transmission (≤ 1400 bytes, compatible with UDP MTU and TCP socket send limits)

2. **Infer error response triggers**
   - Based on the protocol structure and SUT information, prioritize generating messages that intentionally violate protocol SEMANTIC rules (but not syntactic rules) to trigger SPECIFIC, defined error responses:
      - Valid protocol violations (e.g., incomplete URI, invalid method, missing fields) that map to documented error codes
      - Semantic inconsistencies (e.g., length field matching protocol-defined invalid ranges, valid but non-existent resource identifiers) that elicit standard error responses
      - Protocol-specified invalid values (e.g., expired nonce for authentication errors, invalid content type for unsupported media errors)
      - Short, valid payloads with semantic violations (keep total length ≤ 1400 bytes) to ensure the SUT returns a standard error response

   - Prefer generating messages that are:
      - **semantically invalid (per protocol specs)** to trigger defined error responses
      - **Total length ≤ 1400 bytes** (critical for socket transmission success)
      - Tailored to trigger KNOWN, documented error response codes for the protocol

3. Generate a **Python function** that constructs **error-triggering instance**
   - The message must contain semantic violations designed to trigger protocol-defined error responses from the server/client 
   - All fields are concretely instantiated with values chosen to target specific error response codes
   - **The final returned bytes object must have a total length ≤ 1400 bytes** (non-negotiable constraint for socket compatibility)

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, etc.)
* No third-party packages
* No input parameters
* Output must be a **bytes object**
* Do NOT include networking code
* **CRITICAL**: The total length of the returned bytes object must be ≤ 1400 bytes (to comply with socket send limits for both UDP and TCP)

---

### **Function Prototype (Must Match Exactly)**

def mutate_${msg_type}():
    """Generate one error-triggering $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes
    - Total message length ≤ 1400 bytes (compliant with socket send limits)
    - Designed to elicit standard protocol-defined error responses (no program exceptions)
    """
    
    message = b''
    
    # Construct syntactically valid but semantically non-compliant message
    # to trigger standard protocol-defined error responses from SUT
    # Ensure total length ≤ 1400 bytes to comply with socket send limits
    
    return message

---

### **Output Constraints**

Only output the completed Python function code

Do NOT include explanations, markdown, or comments outside the function

The function must be directly executable

The function takes no arguments.

