# Merge order

## Source precedence

```
config files  <  environment variables  <  command-line arguments
```

All config files share the lowest level. Within it, later files win:

1. `files=` in the order given;
2. `env_config` — the one file named by that environment variable;
3. `<PREFIX>CONFIG[__SUBPATH]` pointers, **sorted by variable name**, which sorts by subpath
   depth: the global file first, then `CONFIG__DB`, then `CONFIG__DB__HOST`, so a more
   specific file overrides a broader one regardless of environment iteration order;
4. CLI `--config[.subpath][+]` in left-to-right argv order.

Environment variables are parsed *inside* the pipeline (not before it) because they can
name config files that must be loaded at step 3, before inline env values are applied.

## The single merge pipeline

`_pipeline._merge_sources` is the only implementation of source priority, file-loading
order, locals checks and final reference canonicalization. `confarg.merge()` and the four
adapters' `merge_*` functions each extract their CLI values and `--config` pairs their own
way, then delegate here.

**Rule: fix merge-order or file-loading behavior in this module only.** It then lands in
all front-ends at once.

History: before PR #65 each adapter re-implemented parts of the pipeline and diverged
(custom `config_flag` ignored for env pointers, trailing `+` ignored, `env_config`
unsupported, env config files unsorted, `construct()` called without `__root__`
unwrapping). `TestPipelineParity` in `tests/cli/test_backend_contract.py` pins each of those.
