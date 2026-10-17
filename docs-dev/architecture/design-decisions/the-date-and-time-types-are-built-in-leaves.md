# The date and time types are built-in leaves

`date`, `datetime`, `time`, `timedelta` and `timezone` are registered leaves with no call to `register_leaf_type`, as `Path`, `Decimal` and `UUID` are ([Decimal and UUID are built-in leaves](decimal-and-uuid-are-built-in-leaves.md#decimal-and-uuid-are-built-in-leaves)): `_coerce._LEAF_COERCIONS` and `_LEAF_SERIALIZERS` hold an entry for each (FEAT-51, every choice below maintainer-chosen).
Unregistered, none of them was usable: `date`, `datetime` and `time` have no signature `inspect` reads, so each was an unsupported leaf, refused on every channel and by `dump()`; `timedelta` and `timezone` were refused the same way.
`zoneinfo.ZoneInfo` stays out: whether `ZoneInfo('Europe/Paris')` exists depends on the machine's time zone database (the `tzdata` package on Windows), so a field typed by one would load on one host and not another.

Registered, each is everything a registration makes a type ([Decimal and UUID are built-in leaves](decimal-and-uuid-are-built-in-leaves.md#decimal-and-uuid-are-built-in-leaves)): it outranks every other leaf kind in a union, an expression computes with the object (`${start + span}`), a default is laid as the base layer, and its `__name__` is a `__cast__` name.

## The text each type reads

`date`, `datetime` and `time` read the text their own `fromisoformat` reads, and nothing else: ISO 8601, including its basic format (`20210203`) and week dates (`2021-W05-3`), `Z` and numeric offsets, and a date-only text for a `datetime`, read as its midnight.
A Unix timestamp is refused (`--at 1612347630`), which pydantic and msgspec both accept: a number carries no unit, and a timestamp would come back aware where ISO text without an offset comes back naive.
An offset is kept as written; nothing is converted to UTC or to local time.
Digits finer than a microsecond are truncated, as `fromisoformat` truncates them.

### A file's native value reads as its text

YAML and TOML hand confarg native dates, datetimes and (TOML) times, and a `datetime` is a subclass of `date`.
Each is read as its text would be, so a file and the command line agree:

```python
@dataclass
class Config:
    when: date
    at: datetime
```

| | `when` (a `date`) | `at` (a `datetime`) |
|---|---|---|
| `--when 2021-02-03T10:20:30` / `--at 2021-02-03` | refused | `datetime(2021, 2, 3, 0, 0)` |
| YAML `2021-02-03 10:20:30` / `2021-02-03` | refused, a midnight one too | `datetime(2021, 2, 3, 0, 0)` |

`_coerce_date` refuses a `datetime`, as `date.fromisoformat` refuses `2021-02-03T00:00`; `_coerce_datetime` reads a `date` as its midnight, as `datetime.fromisoformat` reads `2021-02-03`.
Rejected: Python's subclass rule, under which a `date` field keeps a YAML `datetime` as it is while argv's datetime text is refused; refusing both ways, as msgspec does, which would also refuse argv's `2021-02-03` for a `datetime`, against `fromisoformat`; truncating a `datetime` to its date, which drops data with no error.

### An instance is its most specific registered type

`_coerce_registered` used to pass a value through when `isinstance(value, tp)`, which let a `datetime` into a `date` field before the coercion could refuse it, and `_serialize._object_form` took the first registered type the value was an instance of, which wrote a `datetime` with `date.isoformat()`, its time dropped.
`_coerce._registered_leaf_of` is the one answer to "which registered leaf is this value?": the first registered class of its MRO, so a `datetime` is a `datetime` and a `WindowsPath` a `Path`.
Coercion passes a value through only when that answer is the target, serialization writes it with that answer's serializer, `native_types` matches against it, and the default layer asks it whether a default is a leaf ([invariants](../invariants.md#delegate-to-the-canonical-function)).

### A number is no time and no duration

PyYAML reads YAML 1.1, where an unquoted `10:20` is the base-60 integer 620 and `1:30:00` is 5400.
A `time` field refuses an int: ISO reads `10:20` hour first, and 620 read as seconds since midnight would be `00:10:20`.
A `timedelta` field refuses every number too, a file's and argv's `90` alike: a number carries no unit.
Both refusals name the type's form, and, for an int of 60 or more, the YAML reading it may have come from, spelled back in base 60: `Cannot coerce int 620 to time at 't': a time is ISO 8601 text, such as '10:20:30'; YAML reads an unquoted 10:20 as the base-60 number 620, so quote it`.
A quoted duration is still refused, so the duration's message does not say to quote it; its example, `PT1H30M`, is what to write instead.
Every refusal of the five types ends with the form the type reads (`_coerce._LeafRefusal` carries it to `TypeCoercionError.cannot_coerce`).

## A duration is ISO 8601 text

The standard library has no reader for a duration, so `_coerce._parse_duration` is confarg's: `[-]P[<n>W][<n>D][T[<n>H][<n>M][<n>S]]`, case-insensitive, at least one part, a fraction (after `.` or `,`) on the last part only, as ISO 8601-1 allows.
Years and months are refused, their length varying; a week is seven days and mixes with days (`P1W2D`).
A leading minus, from ISO 8601-2 and XML Schema's `xs:duration`, makes the duration negative; a minus inside (`P-1D`) is refused.
The sum is exact, in fractions, and rounded half-even to the microsecond, as `timedelta` itself rounds.
`_format_duration` writes days, then hours, minutes and seconds, a zero part left out, the seconds' fraction trimmed, a negative duration as a minus before its length, zero as `PT0S`: `P1DT2H`, `PT1M30.5S`, `-PT1H30M`.

Rejected: Python's `str()` form (`1:30:00`, `2 days, 0:00:00`) and the colon forms beside ISO.
A two-part `1:30` is ambiguous: base-60 seconds, as YAML reads it, make it 90 seconds, while ISO reads a time of day's `10:20` hour first, so one text would mean two things across a `time` and a `timedelta` field.
`str()`'s negative form, `-1 day, 22:30:00`, signs the days alone, which pydantic misreads as the whole (−2 days + 1:30).
Rejected too: a number as seconds, which msgspec accepts, for the unit it does not carry.

## A timezone is an ISO 8601 offset

A `timezone` field reads the UTC offset a `datetime`'s text ends with, as `datetime.fromisoformat` reads it (`Z`, `+02:00`, `+0200`, `+02`, `+02:00:30.5`), and `Z` in either case.
Python's own `str()`, `UTC` and `UTC+02:00`, is refused, being no ISO 8601.
It is written as `datetime.isoformat()` writes the offset, `+00:00` for UTC rather than RFC 3339's `Z`, so a timezone and a datetime's offset dump alike; a name given at construction (`timezone(+2h, 'CEST')`) is not written, and the value still reads back equal, a `timezone` comparing by its offset.
No precedent reads one: pydantic builds no schema for `timezone`, msgspec refuses a string.

## A writer may hold a date natively

`dump()` writes each of the five as its ISO text, so its dict is ready for any writer, JSON's included, as `Decimal`'s `str()` is.
YAML and TOML hold dates natively, so `dump()` and `dump_file()` take `native_types`, the registered leaf types written as the objects they are, matched by `_registered_leaf_of`: `(date,)` keeps a `date` and writes a `datetime` as text.
`dump_file()` passes its format's set unless given one: `confarg.YAML_NATIVE_TYPES` and `confarg.TOML_NATIVE_TYPES` are `(date, datetime)`, `confarg.JSON_NATIVE_TYPES` is empty.
Neither holds a `time`: PyYAML cannot write one, and `tomli_w` refuses one with an offset.
A datetime whose UTC offset is no whole number of minutes, as `ZoneInfo('Europe/Paris')` gives before 1911 (`+00:09:21`), is written as its text even where its type is native: both writers write such an offset, and neither reads it back (`_serialize._a_writer_holds`).
Rejected: dropping `datetime` from the automatic sets over it, and refusing the value, which the text form writes correctly.
`_serialize._DumpOptions` carries the set down the serializers beside the union tag and the tag policy.
The raw dict `dump_file()` writes takes the set too, so `merge()`'s dict of a YAML file writes its dates back as YAML dates, as it did before the types were leaves.
A type no registry names is refused with a `TypeError`: nothing but a registered leaf is serialized to a form it could be kept from.

Rejected: native objects in `dump()`'s own dict, which `json.dumps(confarg.dump(cfg))` could not write; the automatic sets alone, with no parameter, which leaves a user's own writer (ruamel, tomlkit) without them; a mapping keyed by format instead of three constants, whose typo fails only at run time.

## Precedents

| | `date`/`datetime`/`time` text | a `datetime` field given a date | a duration's text | a number for a duration | dump |
|---|---|---|---|---|---|
| pydantic 2 (run) | ISO, timestamps too | its midnight | ISO and `str()`, `P1M` as 30 days | seconds | ISO strings in JSON mode, objects in Python mode |
| msgspec (run) | RFC 3339 only | refused | ISO, fixed units, no weeks | seconds, text included | ISO strings; `builtin_types` keeps objects |
| cattrs (run) | `date`, `datetime` only, ISO | its midnight | none | none | ISO strings in JSON, objects in its YAML and TOML converters |
| jsonargparse 4.52 (run) | none | — | `str()` only | refused | `str()` |

confarg reads as pydantic does where the standard library has a reader, and refuses what carries no unit, as msgspec does a variable one; it dumps as msgspec does, `native_types` being its `builtin_types`.
