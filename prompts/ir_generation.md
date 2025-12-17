
You are an expert in **network protocol analysis and formal syntax specification**.

Your task is to generate a **protocol message syntax description** using the **protoIR markup language**, based on the protocol information provided.

---

### **Input**

You will be given:

* **Protocol name**: $pro_name
* **Message name** (if applicable): $message_name
* **Protocol description or RFC excerpt**:
$rfc_doc

---

### **Output Requirements**

1. **Message Definition**

   * Use `<message>` as the top-level element.
   * Set the `name` attribute to $message_name (or infer a reasonable name if not provided).
   * Add a brief XML comment describing the **purpose of the message**.

2. **Field Definitions**
   For each protocol field:

   * Use a `<field>` element.
   * Specify:

     * `name`: semantic field name
     * `type`: `"constant"` or `"variable"`
     * `length`: use `B` for bytes, `b` for bits (e.g., `1B`, `16b`)
     * `value`:

       * Constant fields → exact value (decimal / hex / binary)
       * Variable fields → valid range or symbolic range

3. **Semantic Comments**

   * Add an XML comment **immediately after each field** explaining:

     * Its role in the protocol
     * Any semantic meaning (flags, identifiers, lengths, etc.)

4. **Modeling Rules**

   * Prefer **explicit constant fields** for magic numbers, version fields, and fixed flags.
   * Use **variable fields** for lengths, identifiers, payload sizes, and status codes.
   * If a field’s length depends on another field, note this dependency in a comment.
   * Do NOT invent fields not implied by the protocol description.
   * If information is missing, make a **reasonable inference** and document it in a comment.

5. **Output Format Constraints**

   * Output **only valid protoIR XML**
   * Do NOT include markdown formatting
   * Do NOT include explanations outside XML comments

---

### **Expected Output Structure Example**

```xml
<message name="ExampleProtocolMessage">
    <!-- Used for data exchange between client and server -->

    <field name="Header" type="constant" length="3B" value="0x404"/>
    <!-- Magic number identifying the protocol -->

    <field name="Flag" type="constant" length="3b" value="0b101"/>
    <!-- Control flags indicating message type -->

    <field name="DataLength" type="variable" length="2B" value="0x0000-0xFFFF"/>
    <!-- Length of the following payload in bytes -->

    <field name="Status" type="variable" length="3b" value="0b001-0b111"/>
    <!-- Status code representing processing result -->
</message>
```

---

### **Validation Checklist (for the model)**

Before finalizing the output, ensure:

* All fields have `name`, `type`, `length`, and `value`
* Bit/byte units are used consistently
* XML is well-formed
* Comments clearly explain protocol semantics


