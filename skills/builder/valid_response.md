
You are an expert in **network protocol analysis and RFC-based behavior inference**.

Your task is to **infer only the response message types that indicate a successful request outcome**, based strictly on the provided protocol specification.

---

#### **Input**

You will be given:

* **Protocol name**: $pro_name

* **Current request message type**:

  ```
  $current_request
  ```

* **Candidate response message types**:

  ```
  $response_types
  ```

* **Request information**:

  ```
  $info
  ```

---

#### **Task Definition**

* Determine which response message types **may be returned by the server when the request succeeds**.
* Each response type represents a **distinct successful protocol outcome**.
* Include only successful responses explicitly or implicitly defined by the RFC.

---

#### **Selection Rules**

* Select **only** from the provided `Candidate response message types`
* Do **NOT** invent new response types
* If the RFC language is ambiguous, **include the response only if it is clearly implied as a successful outcome**
* Do **NOT** assume implementation-specific behavior

---

#### **Output Requirements**

* Output **only a single valid JSON object**
* Do **NOT** include explanations, comments, or additional text
* The JSON object must contain exactly one field:

  * `possible_response`:
    An array of response message types (strings)

---

#### **Output Format Example**

{
  "possible_response": [
    "230",
    "232"
  ]
}
