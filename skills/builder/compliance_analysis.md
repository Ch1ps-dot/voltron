TASK
Judge whether the captured response violates a normative wire-format, semantic, sequencing, or required-response rule.

INPUT
TARGET: $target_name
PROTOCOL: $protocol
SPEC_NAMES: $rfc_names
EXCHANGE_JSON: $exchange
SPEC_CONTEXT_JSON: $context

RULES
Use non_compliant only with quoted/spec-located normative evidence conflicting with observed bytes. Treat optional or implementation-defined behavior as compliant; use uncertain when state/history/evidence is insufficient. Do not invent causes.

OUTPUT
JSON only matching: $analysis_schema
