TASK
Classify an RFC excerpt by message relevance.

INPUT
RFC: $rfc_num
PROTOCOL: $pro_name
EXCERPT:
$rfc_doc

LABELS
- request: client-originated message syntax, fields, values, payload, construction, processing, preconditions, state effects, or examples.
- response: server reply/ack/error syntax, status fields, values, payload, processing, or examples.
- all: shared/bidirectional format or rules clearly applying to both.
- none: no concrete message, field, payload, or message-processing relevance.

Ignore general overview, transport/deployment, security/IANA, history, references, or pure state-machine prose unless tied to concrete messages. Use only the excerpt; if unclear choose none.

OUTPUT
Exactly one lowercase token: request, response, all, or none.
