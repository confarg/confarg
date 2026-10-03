# A divergence leans towards the affected backend's own idiom

Parity is the rule ([invariants](../invariants.md#cross-channel-parity)): a feature is spelled the same
way in all five front-ends and all three channels. Some spellings cannot reach every front-end,
because a host framework fixes at registration what confarg decides from argv. This decision says
which way to lean when that happens; it does not lower the bar for *whether* it happens, which
still needs a concrete reason and the maintainer's explicit approval, obtained before the
divergence is implemented.

When parity cannot be reached, the front-end that has to give something up keeps **its own way
of working**, so the result stays native to the people who chose that framework. A confarg
spelling is not worth making a click user type something click would never ask them to type.
Concretely: the backend that cannot express the shared spelling declines it, rather than every
backend being dragged down to the narrowest common form.

The tie breaks towards the **CLI-oriented** backend, not towards confarg's config-oriented
philosophy. Command-line parameters are first and foremost user-friendly knobs for tweaking a
configuration at the last minute; they are not a configuration-file format that happens to live
in argv. Inline JSON on a command line is not friendly, so a whole-value `'[13, 42]'` or
`'{"x": 13}'` token is the half that gives way -- not the readable `--pair 13 42` a CLI user
expects, and not a framework's own native convention. Files and the environment remain where a
whole object is spelled comfortably; the CLI is where it is tweaked.

The corollary is that a divergence is **narrowed to the backend that imposes it**, never widened
to keep the five front-ends symmetrical. A front-end that *can* express the spelling gets it.
Symmetry is not the goal -- parity is, and where parity is unreachable the goal is the smallest
number of surprised users.

Worked example: [CLI adapters](../cli-adapters/whole-value-flags.md#whole-value-flags) -- a fixed-arity flag (`tuple[X, Y]`,
namedtuple) registers `nargs="*"` for argparse and cyclopts, which can take both the positional
form and a single whole-value token, while click keeps its exact token count and declines the
whole-value token, because click's only alternative (`multiple=True`) would have cost click
users `--pair 13 42`.
