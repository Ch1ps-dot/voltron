You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation and repair**.

Your task is to **repair and regenerate Python code that constructs a protocol message**, ensuring it strictly conforms to the provided protoIR message description **and the observed server behavior**.

---

### **Input**

You will be given:

* **Protocol name**: $pro_name
* **Message type / message name**: $msg_type
* **Previous Generated Program**: $code
  - This program may contain incorrect field values, invalid ordering, missing constraints, or violations of server expectations.
* **SUT (Server Under Test) Information**: $info
  - This may include:
    - Observed server responses (e.g., error codes, rejection reasons)
    - Accepted / rejected field values
    - Transport-layer behavior
    - State-related constraints inferred from prior interactions

* **protoIR Message Description**
  - Defines the authoritative syntax, field order, data types, and constraints of the message.

---

### **Your Task**

Using the protoIR description **as the primary specification** and the SUT information **as behavioral constraints**:

1. **Analyze the previously generated code**
   - Identify violations of the protoIR specification
   - Identify inconsistencies with the observed server behavior

2. **Repair the message construction logic**
   - Fix incorrect field ordering
   - Adjust field values to satisfy semantic constraints
   - Refine lengths, delimiters, encodings, and dependent fields
   - Ensure compatibility with the current server state if applicable

3. Generate a **Python function** that constructs **one valid instance** of the `$msg_type` message
   - The generated message must be **accepted by the server described in the SUT information**
   - All fields must be concretely instantiated within legal ranges

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

def input_$msg_type():
    """Generate one $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct the message strictly following protoIR
    # and repaired according to the SUT information
    
    return message

Output Constraints

Only output the completed Python function code

Do NOT include explanations, markdown, or comments outside the function

The function must be directly executable

The generated message must be protocol-valid and server-compatible