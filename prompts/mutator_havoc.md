You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation for fault injection**.

Your task is to **generate Python code that constructs a protocol message specifically designed to trigger deep parser and state-machine vulnerabilities** in the Server Under Test (SUT). The message must be **syntactically close enough to bypass shallow validation** but contain **compound, high-risk semantic conflicts** (including garbled characters, tampered message types, framing inconsistencies, and invalid encodings) to reach and break deeper logic.

---

### **Input**

You will be given:

* **Protocol name**: $pro_name
* **Message type / message name**: $msg_type
* **Previous Generated Program**: $code
* **SUT (Server Under Test) Information**: 
   $info

   The SUT information above may include:
   - configuration file of SUT
   - real request messages captured in communication.
   - settings of client or server

---

### **Your Task**

1. **Analyze the previously generated code and protocol structure**
   - Identify syntactically valid but semantically dangerous field values, lengths, encodings, and message type identifiers
   - Pinpoint protocol fields that are likely to trigger unhandled exceptions (e.g., length fields, checksum fields, string delimiters, numeric boundaries, message type flags)
   - Focus on fields related to **message type identification** (to allow tampering) and **string/byte payloads** (to inject garbled characters)
   - Calculate the maximum safe message length for socket transmission (≤ 1400 bytes, compatible with UDP MTU and TCP socket send limits)

2. **Infer fault injection opportunities (ENHANCED REQUIREMENTS)**
   - Based on the protocol structure and SUT information, prioritize generating messages with:
      1. **Tampered message types**: Modify the message type identifier (e.g., use invalid enum values, swap type codes with other message types, set reserved type bits) while keeping the overall structure valid
      2. **Garbled/Invalid encodings**: Inject non-UTF8 bytes (e.g., 0xFF, 0x00, 0xEF BF BD), mixed encodings (GBK in UTF8 fields), or unprintable control characters (0x01-0x1F) into string/payload fields
      3. **Extreme boundary values**: Maximum/minimum allowed values ±1, negative values for unsigned fields, zero-length payloads with non-zero length fields, small but extreme payloads (avoid oversized data) to trigger memory/exhaustion issues without exceeding socket limits
      4. **Inconsistent field dependencies**: Length fields mismatching actual payload length (e.g., length=100 but payload=10 bytes, length=-5), invalid checksum/hash values (random bytes instead of valid checksums)
      5. **Chaotic repetitive patterns**: Short but dense sequences of identical garbage bytes (e.g., 0x41 repeated 50 times) or random mixed bytes in critical fields (keep total length ≤ 1400 bytes)
      6. **Parser ambiguity patterns**: Duplicate critical fields with conflicting values, mixed delimiters/line endings, spacing ambiguities, or repeated separators
      7. **Cross-field conflict chains**: At least one contradiction where a later field invalidates assumptions from an earlier field
      8. **State confusion hints**: Reused stale identifiers/tokens, out-of-order semantics, or unsupported version-feature combinations
   - Ensure the message is **semantically invalid, chaotic, and extreme** (distinct from standard messages) to maximize fault exposure, AND **the total length of the final message must NOT exceed 1400 bytes** (safe socket transmission limit for both UDP and TCP)
   - Build each test case as a **compound anomaly** by combining at least **2 to 4 mutation families** in one message (not a single isolated corruption)

3. **Construct fault-inducing message logic**
    - Preserve protocol-mandated field ordering and basic syntax (to avoid immediate rejection by SUT)
    - Mandatorily inject:
       - At least one type of garbled character/invalid encoding
       - Tampered message type identifier (invalid/non-standard type value)
       - At least one extreme boundary value (e.g., overflow, underflow, inconsistent length)
       - At least one parser-ambiguity or duplicate-conflict pattern
    - Introduce intentional inconsistencies between dependent fields (e.g., length vs payload size)
    - Use valid low-level encodings for malicious content (e.g., null bytes in string fields)
    - **Strictly limit the total length of the final bytes object to ≤ 1400 bytes** (ensure compliance with socket send limits; avoid oversized payloads)

4. Generate a **Python function** that constructs **extremely chaotic, fault-inducing instance** of the `$msg_type` message
   - The message must contain **garbled characters, tampered message type, and extreme semantic anomalies** designed to trigger crashes, hangs, or invalid state transitions in the SUT
   - All fields are concretely instantiated with values chosen to maximize chaos and fault exposure
   - Use deterministic mutation templates with random parameterization; avoid pure random byte blobs
   - **The final returned bytes object must have a total length ≤ 1400 bytes** (critical constraint for socket transmission)

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, `bytes`, `os` etc.)
* No third-party packages
* No input parameters
* Output must be a **bytes object**
* Do NOT include networking code
* Pay attention to handling loop operations in functions and avoid infinite loops.
* **CRITICAL**: The total length of the returned bytes object must be ≤ 1400 bytes (to comply with socket send limits)
* Keep generation robust: no unhandled exceptions during message construction

---

### **Function Prototype (Must Match Exactly)**

def havoc_${msg_type}():
   """Generate one complex, fault-inducing $msg_type message for the $pro_name protocol.
   - Contains compound anomalies: garbled encodings, tampered type, and semantic conflicts
   - Total message length <= 1400 bytes (compliant with socket send limits)
   - Input: none
   - Output: bytes
   """

   message = b''

   # Construct syntactically plausible but semantically conflicting message
   # with compound anomalies and boundary-heavy values.
   # Ensure total length <= 1400 bytes.

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
6. **Total length ≤ 1400 bytes** (non-negotiable, to comply with socket send limits)
7. Include at least one parser ambiguity pattern and one cross-field contradiction
