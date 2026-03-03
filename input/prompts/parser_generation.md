You are an expert Python developer and network protocol analyst.

Your task is to **generate Python code that extracts a status code from a protocol response message**, based on **protocol field format information provided in a structured JSON-like description**.

### **Input**

You will be given:

* **Protocol name**: $pro_name
* **protocol format information**: $res_info

The protocol format information is given as a list of field descriptors. Each field descriptor may contain:

* `field_name`: the semantic name of the field (e.g., "Reply Code", "Status Code")
* `position`: a textual description of where the field appears in the response message (e.g., "first three bytes", "first line before space")
* `explanation`: the semantic meaning of the field
* `value`: a list of valid values

---

### Your Task

Using the provided protocol format information as **the only source of truth**, write **Python code** that:

1. Accepts a **response message** as input (string or bytes).
2. Locates the **status / reply code field** according to the `position` description.
3. Extracts the status code from the response message.
4. Converts the extracted status code into an **string**.
5. Return empty string '' if the status code cannot be located

---

### Constraints

* Use **Python only**
* Use **only built-in libraries**
* Use **packet_parser** as function name
* Do NOT hard-code protocol-specific assumptions beyond what is stated in the field format information
* Input is 'bytes'
* Final output type is `bytes`

---

### Output Constraints

* Output **only the Python code**
* Do NOT include explanations, comments outside the code, or markdown
* The code must be directly executable

