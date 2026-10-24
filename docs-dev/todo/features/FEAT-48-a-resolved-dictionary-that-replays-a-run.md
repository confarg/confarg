---
filed: 2026-10-17
where:
  - src/confarg/_api.py::resolve
  - src/confarg/_default_layer.py
effort: M
needs_design: true  # the API shape, factory and instance defaults, and what a call: becomes
risk: medium
impact: behavior
severity: minor  # no artifact replays a run exactly; dump(obj) records the state, which need not load back
---

# FEAT-48 — A resolved dictionary that replays a run

The dumps have three uses ([the object dump writes state](../../architecture/design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)): the merged dict says what was passed and can be reused, the object dump is forensic, and the resolved dict is the one meant to replay a run.
It falls short of that today in two places: `resolve()` leaves out every default nothing touched ("construction applies it"), so a default the code changes between two runs changes the replay, and it keeps each `call:` as written, so the call runs again on reload, on whatever its target does by then.

```python
@dataclass
class Config:
    memory_gb: int = 4
    workers: int = 0
    heap_mb: int = 0


data = {"workers": {"call": "os.cpu_count"}, "heap_mb": "${int(memory_gb * 1024 * 0.8)}"}
confarg.resolve(Config, data)
# {'workers': {'call': 'os.cpu_count'}, 'heap_mb': 3276}   memory_gb missing, the call kept
```

The design pass decides the API (a keyword on `resolve()`, or a function of its own), whether a `default_factory` default and an instance default are written (the same question as [FEAT-38](FEAT-38-a-factory-default-is-no-base.md) and [FEAT-39](FEAT-39-a-struct-instance-default-is-no-base.md), and an instance default meets the object-dump limits), and whether a `call:` result is pinned, which means running the calls before `build()`, once.
Precedents: jsonargparse's dumped config, which LightningCLI's `SaveConfigCallback` saves beside each run, writes every default and keeps `class_path` / `init_args` specs, so instantiation reruns on replay; Hydra saves the composed config with its `_target_` specs.
Both pin the data and the defaults, not a call's result.
