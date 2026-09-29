# cli_prefix is given at registration and recovered at merge

The adapters take `cli_prefix` on `populate_*` — which owns flag naming — record it, and let
`merge_*`/`from_*` recover it; passing one there that disagrees raises
([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)). The prefix is what makes configuration flags
distinguishable from a host CLI's own, so it belongs in the front-ends built for exactly that
coexistence, not in vanilla alone.

Rejected: **merge-time only**, the arrangement that kept the prefix vanilla-only in the first
place — a prefix that disagrees with what was registered matches no flag, and the fields simply
come back missing, so the failure is silent. Rejected: **both ends, "must match"**, the looser
contract `config_flag` already carries — one keyword more to repeat, with the same silent
failure when the two drift. Recording it at registration removes the repetition *and* makes the
disagreement detectable, so the mismatch became an error rather than a documentation note.

- Cost: `populate_*` has to stash the value somewhere that survives into the merge step, and no
  framework hands that step the object the flags were registered on — three different hiding
  places ([CLI adapters](../cli-adapters/cli-prefix-boundaries.md#the-cli_prefix-boundaries)).
