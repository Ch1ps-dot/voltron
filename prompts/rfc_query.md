You are a protocol analysis expert, and you are currently analyzing the $(pro_name) protocol. Please complete the following tasks:
    1. Query which documents are related to this protocol.
    2. If the specification document of this protocol is an RFC document, check these RFC documents. Ignore documents that have been obsoleted by other documents and return the RFC numbers of the other eligible documents.
    3. If the specification document of this protocol is not an RFC document, directly return the name of the document.
    Finally, return the analysis results in JSON format.
    Below is an example of the output for the analysis of the FTP protocol:
    ```json
    ["959","3659","2389","2428","4217"]
    ```