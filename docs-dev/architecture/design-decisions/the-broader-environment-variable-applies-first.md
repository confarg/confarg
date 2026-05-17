# The broader environment variable applies first

Two environment variables whose paths nest — `APP_USERS-` beside `APP_USERS__0=x`, `APP_USERS='["q", "r"]'` beside `APP_USERS__0=x`, `APP_DB__json` beside `APP_DB__PORT` — merge as the flags of the same paths merge when the broader one is typed first: the deeper variable refines what the broader one wrote (maintainer-chosen, BUG-116).
At one path, a delete comes first, then a `json` cast, then a plain value.
The mechanism is in [environment parsing](../environment-parsing.md#the-broader-variable-applies-first).

The CLI resolves such a pair by "last typed wins", and the environment has no typing order: a mapping's iteration order is an accident of how it was built, so the pair resolved differently from one process to the next.
One order had to be chosen, and the library had already chosen it three times: the `<PREFIX>CONFIG__…` pointers load the broader file first ([merge order](../pipeline/merge-order.md#source-precedence)), `<PREFIX>JSON` folds in under the per-field variables, and the plain root variable refines the root cast (REF-44).
This decision is those three made one rule.

- **Rejected: a delete beats every variable below it.**
  It fixed only the delete pair, leaving a whole value or a cast beside a sub-path variable to the mapping's order.
  And it made the environment disagree with `--users- --users.0-` on the CLI.
- **Rejected: refusing nested pairs.**
  The environment would become stricter than the CLI, which accepts every one of them, against [strict CLI, lenient environment](strict-cli-lenient-environment.md#strict-cli-lenient-environment).
- Precedent: pydantic-settings reads a complex field's JSON value, then deep-updates it with the field's nested-delimiter variables, whatever their order in the environment.
