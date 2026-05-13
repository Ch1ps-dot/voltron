You are an expert Python developer and network protocol analyst.


Your task is to **generate Python code that locates and extracts one or more fields (single or multiple) that determine response type/function and concatenates them as the result**, based only on **protocol field format information provided in a structured JSON-like description**.

### **Input**

You will be given:

- **Protocol name**: $pro_name
- **protocol format information**: $res_info

The protocol format information is given as a list of field descriptors. Each field descriptor may contain:

- `field_name`: the semantic name of the field (e.g., "Reply Code", "Status Code")
- `position`: a textual description of where the field appears in the response message (e.g., "first three bytes", "first line before space", "header: Key")
- `explanation`: the semantic meaning of the field
- `value`: a list of valid values

---

### Your Task

Using the provided protocol format information as **the only source of truth**, write **Python code** that:

1. Accepts a response message (bytes) as input.
2. Locates and extracts all fields listed in `$res_info` that are intended to determine response type or function. This must support:
	- single code-like fields (e.g., `Status-Code`), and
	- combined cases where multiple fields together determine the response type (e.g., `Type` + `Subtype`).
3. For each target field, attempt to parse according to its `position` description using reasonable, protocol-agnostic heuristics (examples: first N bytes, first token on first line, header lines of the form `Key: value`, or applying a simple regex derived from `position`).
4. When multiple fields are identified, extract their values in the order they appear in `$res_info` and concatenate the raw bytes of each extracted value (no separators) to form the final result.
5. If any required field (single or one of a combined group) cannot be located or parsed, return `b""`.

---

### Constraints

- Use Python built-in libraries only
- The function name must be `packet_parser`
- Do not hard-code protocol-specific assumptions; all logic must rely only on the field descriptors in `$res_info`
- Support combining multiple fields when the descriptor set implies they jointly determine response type; the combined field-name should be the comma-separated `field_name` values in the same order as in `$res_info`.
- Input type: `bytes`
- Output type: `bytes` (concatenation of extracted field values, in order)

---

### Output Constraints

- Output only the Python code
- Do not include explanations, comments, or markdown
- The code must be directly executable