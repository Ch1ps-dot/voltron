
Safety and Usage Notice: The following prompt and any code it produces are intended strictly for use within authorized, controlled fuzz-testing research environments. Only execute generated code against systems for which you have explicit permission. Do not use outputs for unauthorized testing, scanning, attacks, or other harmful activities.

You are a developer of a **protocol fuzzer** and an expert in **protocol-driven test case generation for deep bug exposure**.

Your task is to **regenerate Python code that creates complex, high-risk mutated protocol messages using structured randomness, boundary stress, and controlled semantic conflicts**, with the explicit goal of **triggering deeper parser/state-machine bugs and abnormal server behaviors** in the Server Under Test (SUT), including:

* unexpected state transitions
* parser desynchronization
* assertion-like failures, crashes, hangs, or logic corruption paths

---

## **Input**

You will be given:

### **Protocol name**: 

  $pro_name

### **field name**: 

  $field_name

### **Field Value**: 

  $msg_type
  
### **SUT (Server Under Test) Information**:

  $info

  The SUT information may include:

  * server/client configuration files

### **Previous Generated Program**:

   $code

### **Possible response code extracted from RFC documents**

  $poss_response

---

## **Your Task**

### 1. Analyze the Protocol Structure

* Identify **key semantic fields** in protocol messages (e.g., method names, identifiers, lengths, URIs, version numbers, authentication fields).
* Determine which fields:

  * directly influence protocol validation
  * are mapped to **exceptional behaviors**
  * are sensitive to boundary values or malformed content

### 2. Message Generation Strategy

* Prefer generating messages that are:

  * **semantically invalid according to the protocol specification**
  * **likely to reach deep server-side validation logic**
  * **capable of triggering new types of responses**
  * **likely to execute uncommon error-handling branches**
  * **likely to expose parser edge bugs (desync, over-read assumptions, stale state reuse)**
* For each critical field type, explicitly include candidate value families when applicable:

  * numeric fields: very long numeric strings, negative numbers, zero, or out-of-range values
  * length-like fields: underflow (shorter than declared), overflow (longer than declared), and inconsistent framing
  * string/token fields: empty string, very short, extremely long values, invalid charset, mixed separators, and malformed quoting/escaping
  * blob/payload fields: generate payloads that can be super long (thousands to tens of thousands of bytes/characters, or more if useful), and do not truncate them to a "reasonable" length
  * identifier/version fields: missing, duplicated, stale/reused, malformed format, and unsupported version tags

### 3. Generate a Python Function

* Produce a single Python function that:

  * constructs **one mutated, error-triggering `$msg_type` message**
  * uses **randomized values, boundary-covering mutations, and out-of-range values** for key fields
  * implements **compound anomalies** (multiple coordinated mutations in one message)
  * returns a `bytes` object
  * **Do not raise exceptions during generation**
  * The program logic should not be overly complex to avoid excessively long execution times.
  * Prefer deterministic mutation templates plus randomness (not fully unconstrained random bytes).

---

### **Code Constraints**

* Use **Python only**
* Use **only built-in libraries** (`random`, `string`, `struct`, etc.)
* No third-party packages
* No input parameters
* Do NOT include networking code
* The function must be directly executable
* If helper logic is needed, keep it inside the same function body
* For fields that accept free-form text, opaque bytes, or payload content, prefer very large outputs and allow them to exceed typical application limits.

---

### **Function Prototype (Must Match Exactly)**

```python
def mutate():
  """
  Generate one complex error-triggering $msg_type message for the $pro_name protocol.
    - Input: none
    - Output: bytes
    - Key fields are randomly generated with boundary coverage
    - Designed to trigger deep parser/state-machine abnormal behaviors
  """
    
  message = b''

  # Construct a semantically inconsistent, compound-anomaly protocol message
  # using boundary-heavy values to trigger deep error-handling paths

  return message
```
