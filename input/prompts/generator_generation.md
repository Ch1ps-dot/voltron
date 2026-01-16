
You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation**.

Your task is to **generate Python code that constructs a protocol message strictly following the provided protoIR message description**.

---

### **Input**

You will be given:

* **Protocol name**: $pro_name
* **Message type / message name**: $msg_type
* **Message syntax specification in protoIR format**:
  $msg_ir

The msg_ir describes the **exact message format**, including field order, field types, lengths, and allowed values.

* **SUT (Server Under Test) Information**: 
  $info
  
  - The SUT information above may include:
    - configuration file of SUT

---

### **Your Task**

Using the protoIR description:

* Generate a **Python function** that constructs **one valid instance** of the $msg_type message.
* The generated message must **respect the field order and semantics defined in the IR**.
* The function must synthesize **concrete field values** for all variable fields within the legal constraints specified in the IR.

---

### **IR-to-Code Mapping Rules (Strict)**

For each `<field>` in `$msg_ir`:

1. **Field Order**

   * Fields must be serialized **exactly in the order they appear** in the IR.

2. **Constant Fields**

   * Emit the exact constant value defined in `value`.
   * Interpret values as follows:

     * Character literals → emit directly as bytes
     * Hex (e.g., `0x0D0A`) → convert to bytes
     * Decimal / binary → convert to bytes with correct length

3. **Variable Fields**

   * Generate a **random but valid value**:

     * Numeric ranges → use `random.randint`
     * Character sets → use `random.choices`
     * Symbolic descriptions → choose a reasonable representative value
   * If `length` is:

     * Fixed → generate exactly that many bytes
     * `undefined` → choose a reasonable length consistent with comments and protocol conventions

4. **Length Dependencies**

   * If a field’s semantic comment indicates that its value depends on another field (e.g., payload length):

     * Compute the dependent value correctly before serialization.

5. **Encoding Rules**

   * All fields must be concatenated into a single **bytes** object.
   * Textual fields should be encoded using ASCII unless the IR implies otherwise.

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, etc.)
* No third-party packages
* No input parameters
* Output must be a **bytes object**

---

### **Function Prototype (Must Match Exactly)**

def generate_$msg_type():
    """Generate one $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Python code that constructs the message
    # strictly following the provided protoIR specification
    
    return message

---

### **Output Constraints**

* **Only output the completed Python function code**
* Do NOT include explanations, comments outside the function, or markdown
* The function must be directly executable
* Use generate_$msg_type as function name

---

### **Self-Check Before Output**

Ensure that:

* Every protoIR field is reflected in the code
* No extra fields are introduced
* Constant fields are not randomized
* Variable fields respect IR constraints
* Final output type is `bytes`
