---
filed: 2026-10-17
where:
  - .pre-commit-config.yaml  # the pretty-format-yaml hook's args
effort: S
risk: low  # repository tooling; the library is untouched
impact: none
severity: trivial  # only the repository's own YAML files meet it; no committed file holds a bare boolean word today
introduced_by: [PR-61]  # ci: Add linting, which added the hook
---
# BUG-249 — The YAML formatter strips quotes the YAML loader needs

The `pretty-format-yaml` pre-commit hook formats YAML as 1.2 (it is built on ruamel.yaml), where a bare `no` is a string, so it drops the quotes from `input: "no"`. confarg loads YAML with PyYAML's `safe_load`, which reads YAML 1.1, where a bare `no` is the boolean `False`. The hook therefore changes what a committed example or test fixture means, and the example's console block then fails or, worse, passes on the wrong reading. It bit the stealing-rule tutorial while it was being written (BUG-230): its `str_or_bool.yaml` was rewritten under it. Fix direction: pass `--preserve-quotes` to the hook, or exclude the YAML files whose quoting matters.

Origin: latent since PR-61, which added the hook beside `check-yaml` to format the repository's YAML; the YAML 1.1/1.2 difference over bare boolean words was not in view. No committed file holds a bare `yes`, `no`, `on` or `off` today.

```console
$ printf 'input: "no"\n' > examples/7_stealing_rule/str_or_bool.yaml
$ uv run pre-commit run pretty-format-yaml --files examples/7_stealing_rule/str_or_bool.yaml
Pretty format YAML.......................................................Failed
- hook id: pretty-format-yaml
- exit code: 1
- files were modified by this hook

File examples/7_stealing_rule/str_or_bool.yaml is not pretty-formatted
Fixing file examples/7_stealing_rule/str_or_bool.yaml
$ cat examples/7_stealing_rule/str_or_bool.yaml
input: no
$ cd examples/7_stealing_rule && uv run str_or_bool.py --config str_or_bool.yaml
# expected: Config(input='no')   (what the file said before the hook ran)
# actual:   Config(input=False)
```
