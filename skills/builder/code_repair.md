TASK
Repair generated Python after local validation fails.

INPUT
FUNCTION: $function_name
CODE:
$code
ERROR:
$error

CONTRACT
- Return a complete replacement with a callable function named `$function_name` and the original signature.
- Fix the reported syntax, name, return-value, or runtime cause.
- Preserve working protocol construction/classification logic; do not use a placeholder.
- Use only the Python standard library.

OUTPUT
Executable Python only; no Markdown or prose.
