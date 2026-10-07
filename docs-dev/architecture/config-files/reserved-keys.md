# Reserved file-only keys

`__include__`, `__root__` (a non-struct target's value at a document root, and a fragment's
whole content when mounted -- see [include semantics](include-semantics.md#include-semantics)),
`__cast__`/`__value__`
([types](../types/stealing-rule.md#cast-pinning-in-files)) and the four list ops `__append__`,
`__delete__`, `__delete_after__` and `__base__`
([deep merge](../pipeline/deep-merge.md#no-channel-types-an-op)) are dunder keys, and only a
configuration file writes one. `_defaults.RESERVED_KEYS` lists them, and
`_parse_cli._reserved_segment` is the one test the other routes are put to: a flag
(`--d.__cast__`), an environment variable and a mount point (`--config.d.__base__`,
`<PREFIX>CONFIG__…`) whose path spells one is refused. The default env separator is also `__`,
so with it a variable cannot spell a dunder at all; a custom separator can, and is refused the
same way.

The refusal is what makes the keys mean the same thing wherever they reach the merge. Until
FEAT-3 the CLI could type them below a dict, and `--d.__cast__ int --d.__value__ 5` built a
`dict[str, int]` field as the integer 5. Anything that must work in every channel (such as the
locals namespace) therefore avoids the dunder form. A field named like a reserved key cannot be
set, which [real field wins](../design-decisions/real-field-wins.md) does not rescue: a file
always read the key as its own
([design decisions](../design-decisions/merge-ops-are-markers-no-channel-types.md#merge-ops-are-markers-no-channel-types)).
