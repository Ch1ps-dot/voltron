You are an expert Python developer and network protocol analyst.


Your task is to **generate Python code that extracts all status-related fields from a protocol response message and concatenates them as the result**, based only on **protocol field format information provided in a structured JSON-like description**.

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

1. Accepts a response message (bytes) as input.
2. Locates and extracts all fields related to "status/reply code" according to their `position` descriptions.
3. Concatenates the contents of all status-related fields in order (as bytes) as the final result.
4. If any status field cannot be located, returns empty bytes('').

---

### Constraints

* Use Python built-in libraries only
* The function name must be packet_parser
* Do not hard-code protocol-specific assumptions; all logic must rely only on the field descriptors
* Input type: bytes
* Output type: bytes

---

### Output Constraints

* Output only the Python code
* Do not include explanations, comments, or markdown
* The code must be directly executable

