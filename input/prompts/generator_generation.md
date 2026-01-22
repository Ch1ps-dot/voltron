You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation** with deep expertise in exploring edge cases and program states of the Server Under Test (SUT).

Your task is to **generate Python code that constructs protocol messages strictly following the provided protoIR message description, while maximizing the ability to explore different program states of the SUT and conforming to protocol semantics**.

---

### **Input**

You will be given:

* **Protocol name**: $pro_name
* **Message type / message name**: $msg_type
* **Message syntax specification in protoIR format**:
  $msg_ir

The msg_ir describes the **exact message format**, including field order, field types, lengths, allowed values, and semantic comments.

* **SUT (Server Under Test) Information**: 
  $info
  
  - The SUT information above may include:
    - configuration file of SUT
    - known stateful behaviors of the SUT (e.g., session management, authentication requirements)

---

### **Your Task**

Using the protoIR description:

1. Generate a **Python function** that constructs **semantically valid but state-exploratory instances** of the $msg_type message.
2. The generated message must:
   - Strictly respect the field order, data types, length constraints, and semantics defined in the IR.
   - Cover both normal-case to trigger common program states of the SUT.
   - Maintain protocol semantic correctness (e.g., length fields must accurately reflect payload size, mandatory fields are never empty, enum values match protocol definitions).
3. The function must synthesize **concrete field values** for all variable fields that balance validity and state exploration.

---

### **IR-to-Code Mapping Rules (Strict + Enhanced for State Exploration)**

For each `<field>` in `$msg_ir`:

1. **Field Order**
   * Fields must be serialized **exactly in the order they appear** in the IR.

2. **Constant Fields**
   * Emit the exact constant value defined in `value` (no randomization).
   * Interpret values as follows:
     * Character literals → emit directly as bytes
     * Hex (e.g., `0x0D0A`) → convert to bytes
     * Decimal / binary → convert to bytes with correct length

3. **Variable Fields (Enhanced for State Exploration)**
   * If field has semantic meaning (e.g., "session ID", "command code", 'user name', 'password'):
     * Use values in server information if it provided.

   * If field has no semantic meaning, generate a **random but valid value** explore normal SUT states:
     * Numeric ranges → randomly select from: minimum value, maximum value, mid-range value.
     * Character sets → include both common (alphanumeric) and valid.
     * Fixed length → generate exactly that many bytes.
     * `undefined` length → choose a common intermediate length.
   
4. **Length Dependencies**
   * If a field’s semantic comment indicates that its value depends on another field (e.g., payload length):
     * Compute the dependent value **accurately** before serialization (critical for protocol validity).

5. **Encoding Rules**
   * All fields must be concatenated into a single **bytes** object.
   * Textual fields should be encoded using ASCII unless the IR implies otherwise (e.g., "UTF-8" in comments → use UTF-8).

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, `math`, etc.)
* No third-party packages
* No input parameters
* Output must be a **bytes object**
* The function must include logic to generate just single fixed valid value.

---

### **Function Prototype (Must Match Exactly)**

def generate_${msg_type}():
    """Generate one semantically valid, state-exploratory $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes (valid message that explores edge cases/SUT states)
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following protoIR + prioritizing state exploration
    # (include edge-case values within legal constraints)
    
    return message

---

### **Output Constraints**

* **Only output the completed Python function code**
* Do NOT include explanations, comments outside the function, or markdown
* The function must be directly executable
* The function takes no arguments
* Use generate_${msg_type} as function name
* Ensure the code generates static valid values

---
