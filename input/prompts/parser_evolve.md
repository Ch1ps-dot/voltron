You are an expert Python developer and network protocol analyst.

Your task is to **modify the original parser code** after receiving feedback about a **failed-to-parse response message** (a message that the original parser returns empty string incorrectly or crashes), to fix parsing issues for that abnormal message, based on **protocol field format information provided in a structured JSON-like description**.

### **Input**

You will be given:

1. **Protocol name**: $pro_name
2. **protocol format information**: $res_info
3. **Original parser code**: $original_code
4. **Failed-to-parse response message**: $message

The protocol format information is given as a list of field descriptors. Each field descriptor may contain:

* `field_name`: the semantic name of the field (e.g., "Reply Code", "Status Code")
* `position`: a textual description of where the field appears in the response message (e.g., "first three bytes", "first line before space")
* `explanation`: the semantic meaning of the field
* `value`: a list of valid values

---

### Your Task

When modifying the original `packet_parser` code:
1. **Preserve core logic**: Keep the original parsing rules based on $res_info (do not rewrite from scratch)
2. **Fix root cause**: Identify why failed message cannot be parsed (e.g., edge case not handled, position parsing logic error, encoding issue) and fix it
3. **Enhance robustness**: Ensure the modified code can correctly parse failed message AND maintain compatibility with previously parsable messages
4. **Maintain constraints**: 
   - Still use only Python 3.x built-in libraries
   - Function name remains `packet_parser`
   - Input type: bytes, Output type: str (empty string only for truly invalid status code)

---

### Constraints

* Use **Python only**
* Use **only built-in libraries**
* Use **packet_parser** as function name
* Do NOT hard-code protocol-specific assumptions beyond what is stated in the field format information
* Input is 'bytes'
* Final output type is `str`

---

### Output Constraints

* Output **only the Python code**
* Do NOT include explanations, comments outside the code, or markdown
* The code must be directly executable