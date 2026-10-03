# Dump round-trips at the built object

`dump_file(merge(...), path)` writes a coerced leaf in its scalar form (`Path` → string,
`Enum` → value), so re-reading the file gives a plain `str` and the merged dicts are not
equal; the *built* objects are. The alternative — re-coercing values read from config files
so the dict itself round-trips — was rejected: it would make file values type-directed and
break the token model, whose whole point is that a self-describing file is never
re-interpreted ([types](../types/token-model.md#token-model)). Round-trip fidelity is
claimed one seam later instead ([pipeline](../pipeline/api-seams.md#public-api-seams)).

A force-cast is the one value that is *not* degraded to its scalar form: a `_Pinned` is written
back as its `{__cast__, __value__}` file spelling, because the bare scalar would be stolen by an
earlier union variant and the built objects would then differ too
([types](../types/stealing-rule.md#cast-pinning-in-files)).

Precedents: pydantic draws the same line with `model_dump(mode="json")` — `Path`, `Enum` and
`UUID` degrade to scalars on the way out and are re-validated, not re-typed, on the way in;
cattrs likewise pairs a lossy `unstructure` with a typed `structure`, never claiming that the
unstructured forms compare equal to the originals.
