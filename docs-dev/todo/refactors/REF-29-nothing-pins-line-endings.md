# REF-29 — Nothing pins line endings, so the CRLF conversion can come back

**Where:** repository root (no `.gitattributes`), `.pre-commit-config.yaml` (`mixed-line-ending`)
**Effort:** S · **Risk:** low · **Impact:** none

The conversion this ticket was filed for has landed: every tracked text file is LF, `examples/`
included, so `uv run pre-commit run --all-files` no longer rewrites anything and the gate starts
out green. What is left is the part that was always separate — nothing *pins* that answer.

The repository has no `.gitattributes`, so the line endings a file is stored with are whatever
the tool that wrote it chose. On Windows that is easy to get wrong in both directions: Python's
`Path.write_text` emits CRLF unless it is passed `newline="\n"`, and `jj file show` translates
its stdout, so a file reconstructed from a revision comes back CRLF. Either one puts 200-file
diffs back on the board beside a one-line change, and `mixed-line-ending --fix=lf` then
"fixes" them into the contributor's working copy.

Fix direction: decide whether a `.gitattributes` pinning `* text=auto eol=lf` (with the binary
suffixes under `docs/assets/` excluded) is wanted. It makes the answer structural instead of a
hook that notices afterwards — the argument the architecture notes make for every other
canonical decision. The alternative is to leave it to the hook and accept that a tool writing
CRLF is caught only on the next `--all-files` run.

What the conversion left, checked over every tracked file rather than over `examples/` alone:

```console
$ uv run python -c "
import subprocess
from pathlib import Path
names = subprocess.run(['jj', 'file', 'list'], capture_output=True, check=True).stdout.decode().split()
crlf = [n for n in names if (p := Path(n)).is_file() and b'\r\n' in p.read_bytes()]
print(f'{len(crlf)} of {len(names)} tracked files hold CRLF: {crlf}')
"
2 of 703 tracked files hold CRLF: ['docs\\assets\\logo.png', 'docs\\assets\\logo_thick.png']
```

Both hits are PNGs, where the byte pair is image data — a `.gitattributes` would have to exclude
them rather than normalize them.
