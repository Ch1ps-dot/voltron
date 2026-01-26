
You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation for fault injection**.

Your task is to **generate Python code that constructs a protocol message specifically designed to trigger edge cases, invalid states, and unexpected program behaviors** in the Server Under Test (SUT), while adhering to the syntactic structure of the protocol (to bypass basic validation and reach deeper logic).

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
    - real request messages captured in communication.
    - settings of client or server

---

### **Your Task**

1. **Analyze the previously generated code and protocol structure**
   - Identify syntactically valid but semantically dangerous field values, lengths, and encodings
   - Pinpoint protocol fields that are likely to trigger unhandled exceptions (e.g., length fields, checksum fields, string delimiters, numeric boundaries)
   - Identify which parts of the message can be manipulated to cause buffer overflows, integer overflows, null pointer dereferences, or logic errors in the SUT

2. **Infer fault injection opportunities**
   - Based on the protocol structure and SUT information, reason about:
      - Boundary values (maximum/minimum allowed values + 1/-1, zero, negative values for unsigned fields)
      - Inconsistent field dependencies (e.g., length field mismatching actual payload length)
      - Invalid encodings (non-UTF8 bytes in string fields, malformed checksum/hash values)
      - Unexpected optional fields (adding/removing optional fields not handled by the SUT)
      - Repetitive patterns (long sequences of identical bytes to trigger memory exhaustion)

   - Prefer generating messages that are:
      - **syntactically protocol-valid** (to pass initial parsing)
      - **semantically invalid** (to trigger unexpected behavior)
      - Distinct from standard messages to maximize fault exposure

3. **Construct fault-inducing message logic**
   - Preserve protocol-mandated field ordering (to avoid immediate rejection)
   - Inject edge-case/invalid values into critical fields
   - Introduce intentional inconsistencies between dependent fields (e.g., length vs payload size)
   - Use valid encodings for malicious content (e.g., null bytes in string fields, oversized payloads)

4. Generate a **Python function** that constructs **one fault-inducing instance** of the `$msg_type` message
   - The generated message must be **syntactically protocol-compliant** (to reach deep SUT logic)
   - The message must contain **semantic anomalies** designed to trigger unexpected behavior (crashes, hangs, invalid state transitions)
   - All fields are concretely instantiated with values chosen to maximize fault exposure

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, etc.)
* No third-party packages
* No input parameters
* Output must be a **bytes object**
* Do NOT include networking code

---

### **Function Prototype (Must Match Exactly)**

def generate_${msg_type}():
    """Generate one fault-inducing $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct syntactically valid but semantically dangerous message
    # to trigger unexpected behavior in the SUT
    
    return message

---

### **Output Constraints**

Only output the completed Python function code

Do NOT include explanations, markdown, or comments outside the function

The function must be directly executable

The function takes no arguments.

The generated message must be syntactically protocol-valid but designed to trigger unexpected SUT behavior
