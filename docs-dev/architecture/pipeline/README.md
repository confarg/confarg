# Pipeline and contracts

How a configuration travels from its three channels to a typed object, and what each stage
promises the next one. Implementation: `_api.py`, `_pipeline.py`, `_merge.py`.

| Note | What it holds |
|---|---|
| [stages.md](stages.md) | the stage diagram, and why every seam between stages is a plain `dict` |
| [api-seams.md](api-seams.md) | which public function stops where, and what round-trips at which seam |
| [merge-build-contract.md](merge-build-contract.md) | `merge()` returns an unvalidated dict: what a parser may reject, and what it must defer |
| [merge-order.md](merge-order.md) | source precedence, file-loading order, and the one module that implements them |
| [deep-merge.md](deep-merge.md) | dict-wins merging, the list-patch sentinel vocabulary, and what a scalar in the way means |
