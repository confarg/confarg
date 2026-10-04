# Line endings are pinned in `.gitattributes`

Text files are LF: `* text=auto eol=lf`, with the PNGs under `docs/assets/` marked `-text`.
The pin binds git-side tooling only — a git clone checks out LF, and `git add` normalizes CRLF —
because jj ignores `.gitattributes` and `core.autocrlf` in both directions (observed on
jj 0.45.1: a CRLF working copy is snapshotted as CRLF despite `eol=lf`, and an LF blob checks
out as LF despite `eol=crlf`). The `mixed-line-ending --fix=lf` pre-commit hook therefore stays
the enforcement for the jj workflow this repository actually runs on; the file declares the
answer to everything else. Precedents: Kubernetes pins `* text=auto eol=lf`; CPython pins
`* -text`, opting out of conversion rather than choosing a direction. Cost: the binary
exclusion list must grow with every new binary suffix, and a jj contributor gets no protection
from the file alone.
