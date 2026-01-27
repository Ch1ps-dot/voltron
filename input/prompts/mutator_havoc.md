You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation for fault injection**.

Your task is to **generate Python code that constructs a protocol message specifically designed to trigger edge cases, invalid states, and unexpected program behaviors** in the Server Under Test (SUT). The message must be **syntactically compliant with the protocol structure (to bypass basic validation)** but contain **extreme, chaotic, and malicious semantic content** (including garbled characters, tampered message types, and invalid encodings) to reach and break deeper logic.

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
   - Identify syntactically valid but semantically dangerous field values, lengths, encodings, and message type identifiers
   - Pinpoint protocol fields that are likely to trigger unhandled exceptions (e.g., length fields, checksum fields, string delimiters, numeric boundaries, message type flags)
   - Focus on fields related to **message type identification** (to allow tampering) and **string/byte payloads** (to inject garbled characters)

2. **Infer fault injection opportunities (ENHANCED REQUIREMENTS)**
   - Based on the protocol structure and SUT information, prioritize generating messages with:
      1. **Tampered message types**: Modify the message type identifier (e.g., use invalid enum values, swap type codes with other message types, set reserved type bits) while keeping the overall structure valid
      2. **Garbled/Invalid encodings**: Inject non-UTF8 bytes (e.g., 0xFF, 0x00, 0xEF BF BD), mixed encodings (GBK in UTF8 fields), or unprintable control characters (0x01-0x1F) into string/payload fields
      3. **Extreme boundary values**: Maximum/minimum allowed values ±1, negative values for unsigned fields, zero-length payloads with non-zero length fields, oversized payloads (10000+ bytes) to trigger memory exhaustion
      4. **Inconsistent field dependencies**: Length fields mismatching actual payload length (e.g., length=100 but payload=10 bytes, length=-5), invalid checksum/hash values (random bytes instead of valid checksums)
      5. **Chaotic repetitive patterns**: Long sequences of identical garbage bytes (e.g., 0x41 repeated 1000 times) or random mixed bytes in critical fields
   - Ensure the message is **semantically invalid, chaotic, and extreme** (distinct from standard messages) to maximize fault exposure

3. **Construct fault-inducing message logic**
   - Preserve protocol-mandated field ordering and basic syntax (to avoid immediate rejection by SUT)
   - Mandatorily inject:
     - At least one type of garbled character/invalid encoding
     - Tampered message type identifier (invalid/non-standard type value)
     - At least one extreme boundary value (e.g., overflow, underflow, oversized payload)
   - Introduce intentional inconsistencies between dependent fields (e.g., length vs payload size)
   - Use valid low-level encodings for malicious content (e.g., null bytes in string fields, oversized payloads packed via struct)

4. Generate a **Python function** that constructs **extremely chaotic, fault-inducing instance** of the `$msg_type` message
   - The message must contain **garbled characters, tampered message type, and extreme semantic anomalies** designed to trigger crashes, hangs, or invalid state transitions in the SUT
   - All fields are concretely instantiated with values chosen to maximize chaos and fault exposure

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, `bytes`, `os` etc.)
* No third-party packages
* No input parameters
* Output must be a **bytes object**
* Do NOT include networking code

---

### **Function Prototype (Must Match Exactly)**

def generate_${msg_type}():
    """Generate one extremely chaotic, fault-inducing $msg_type message for the $pro_name protocol.
    - Contains garbled characters, tampered message type, and extreme boundary values
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct syntactically valid but semantically chaotic message
    # with garbled encodings, tampered message type, and extreme values
    
    return message

---

### **Output Constraints**

Only output the completed Python function code

Do NOT include explanations, markdown, or comments outside the function

The function must be directly executable

The function takes no arguments.

The generated message must:
1. Be syntactically protocol-valid (to bypass basic validation)
2. Contain garbled characters/invalid encodings
3. Have a tampered/invalid message type identifier
4. Include extreme boundary values or inconsistent field dependencies
5. Be designed to trigger unexpected SUT behavior (crashes, hangs, logic errors)
