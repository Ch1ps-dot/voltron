# Learning bundles

Learning bundles package reusable learned model data, equipment, diagnostics,
and selected metrics. They let a verified result be moved between workspaces
without using the source workspace's runtime paths.

## Export

Run learning without fuzzing and write `learning_bundle.tar.gz` to the active
result directory:

```bash
uv run cli.py -s lightftp --learn-and-export -t 30
```

The exported manifest records the target, protocol, and SHA-256 checksum of
every bundled file. A complete bundle contains `evolved_hypothesis.pkl`; a
partial bundle contains validated `partial_guidance.pkl` and is not a
converged model.

No-spec exports carry `knowledge_mode: "no_spec"` and the LLM-only bootstrap
catalog. Reusing one must be reported as **No-spec (cached LLM-only bundle)**,
not as strict No-spec.

## Verify and activate an import

```bash
uv run cli.py -s lightftp \
  --import-learning-bundle /path/to/learning_bundle.tar.gz \
  --activate-import \
  --batch-id example
```

The importer first extracts and validates the archive under
`component/import-staging/`, including manifest hashes and generated component
contracts. Activation then publishes an immutable, target-scoped batch at:

```text
component/models/<target>/<batch-id>/
```

`--batch-id` must be used with both `--import-learning-bundle` and
`--activate-import`. If it is omitted, the importer derives an ID from the
bundle filename and its SHA-256 prefix. A batch ID is 1--64 ASCII letters,
digits, dots, underscores, or hyphens and must begin with a letter or digit.

## Select an imported batch

```bash
uv run cli.py -s lightftp -t 30 --model-batch example
```

The selected batch loads its model and equipment together from the same
provenance boundary. Do not mix a batch model with the global equipment cache.
Keep the original archive and provenance file so the batch can be recreated.
