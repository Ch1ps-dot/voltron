You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation and repair**.

Your task is to **repair and regenerate Python code that constructs a protocol message**, ensuring it strictly conforms to the protocol specification message and discover more possible state transition.

---

## **Input**

You will be given:

### **Protocol name**: 
   $pro_name
### **Message type / message name**: 
   $msg_type
### **Previous Generated Program**:

   - This program may contain incorrect field values, invalid ordering, missing constraints, or violations of server expectations.

   ```
   $code
   ```
  
### **SUT (Server Under Test) Information**: 

   - The SUT information above may include settings of client or server

   $info

   

### **Observed trace of request and server response**

   - Each trace element reflects a semantic transition, e.g.
      (AAA / 888) → (BBB / 666)
      meaning a AAA request triggered a 888 response, followed by a PASS request that triggered a 666 response.

   $trace
   

### **Generated program of semantic related request message**
   ```
   $related_code
   ```
---

## **Your Task**

1. **Analyze the previously generated code and observed state transitions**
   - Identify inconsistencies with the observed server behavior
   - identify the semantic relation in network trace.
   - Identify which parts of the message likely caused the server to remain in the same state, enter an error state, or reject the transition.

2. **Infer opportunities for new state transitions**

   - Based on the observed trace, reason about:
      - which constraints may be relaxed or altered to reach alternative responses
      - which field values, encodings, or optional elements could trigger different server-side behaviors

   - Prefer generating messages that are:
      - protocol-valid
      - state-compatible
      - semantically distinct from previously attempted messages, increasing the chance of discovering new transitions.

3. **Repair the message construction logic**
   - Fix incorrect field ordering
   - Adjust field values to satisfy semantic constraints
   - Refine lengths, delimiters, encodings, and dependent fields
   - Ensure compatibility with the current server state if applicable

4. Generate a **Python function** that constructs **one valid instance** of the `$msg_type` message
   - The generated message must be **accepted by the server described in the SUT information**
   - All fields must be concretely instantiated within legal ranges

---

## **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, etc.)
* No third-party packages
* No input parameters
* Output must be a **bytes object**
* Do NOT include networking code

---

## **Function Prototype (Must Match Exactly)**

def generate_${msg_type}():
    """Generate one $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes
    """
    
    message = b''
    
    # Construct the message strictly following protoIR
    # and repaired according to the SUT information
    
    return message

## **Output Constraints**

Only output the completed Python function code

Do NOT include explanations, markdown, or comments outside the function

The function must be directly executable

The function takes no arguments.

The generated message must be protocol-valid and server-compatible