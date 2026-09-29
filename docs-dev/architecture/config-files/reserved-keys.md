# Reserved file-only keys

`__include__`, `__root__` (a non-struct target's value at a document root, and a fragment's
whole content when mounted -- see [include semantics](include-semantics.md#include-semantics)) and
`__cast__`/`__value__`
([types](../types/stealing-rule.md#cast-pinning-in-files)) are dunder keys and are file-only
by construction: the default env separator is also `__`, so a dunder name cannot be written
as an environment variable. Anything that must work in every channel (such as the locals
namespace) therefore avoids the dunder form.
