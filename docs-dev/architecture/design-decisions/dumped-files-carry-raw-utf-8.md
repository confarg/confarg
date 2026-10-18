# Dumped files carry raw UTF-8

`dump_file` writes every format as UTF-8 with the text spelled as it stands: `_render_yaml` passes `allow_unicode=True`, `_render_json` passes `ensure_ascii=False`, and `_dump_file` opens every file with `encoding="utf-8"` (and `newline="\n"`, the byte-level concern of [line endings](line-endings-pinned-in-gitattributes.md#line-endings-are-pinned-in-gitattributes)).
The TOML writer needs no choice of its own: `tomli_w` escapes nothing, and TOML is specified as UTF-8 — the decision brings YAML and JSON to what TOML already did, so a non-ASCII value reads the same in a dumped file whatever the format.
Before it, both writers escaped (`naïve` as `na\xEFve`, then `na\u00efve`), so the `encoding` argument was unobservable: the byte stream was pure ASCII, and no test could tell whether the argument was there.

Precedents: `python -m json.tool` ships `--no-ensure-ascii` as the opt-out to the same default; PyYAML's `allow_unicode` is the same switch for YAML.
Cost: a reader that assumes a non-UTF-8 locale code page sees mojibake — but YAML and JSON carry no encoding declaration to honor, so the escape was not a fix for such a reader either, only less readable output for everyone else.
