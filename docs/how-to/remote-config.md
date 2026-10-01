---
icon: lucide/cloud-download
---

# Load configuration from a URL

Everywhere `confarg` takes a configuration file path, it also takes a URL. `file:`, `http:` and
`https:` work out of the box, `s3:` with one extra dependency, and anything else through a
handler you register yourself.

Nothing about the rest of the configuration changes: a document fetched over the network is a
configuration layer like any other, so it merges below environment variables and command-line
arguments, resolves `${...}` expressions, and can be mounted under a key.

## Name a URL instead of a path

Every channel that accepts a path accepts a location:

```python
import confarg

# In code
cfg = confarg.load(AppConfig, files=["https://cfg.example.com/app.yaml"])
```

```bash
# On the command line
myapp --config https://cfg.example.com/app.yaml
myapp --config.db s3://my-bucket/db.yaml        # mounted under `db`

# In the environment
export MYAPP_CONFIG=https://cfg.example.com/app.yaml
export MYAPP_CONFIG__DB=https://cfg.example.com/db.yaml
```

```yaml
# Or from inside another configuration file
__include__: https://cfg.example.com/base.yaml
```

Locations and paths mix freely, and all of them sit at the same priority level — the config-file
level — so they are applied left to right and the last one wins:

```python
cfg = confarg.load(
    AppConfig,
    files=["https://cfg.example.com/base.yaml", "./local-overrides.yaml"],
)
```

One restriction: a URL passed to `files=` must be a `str`. `Path("https://h/app.yaml")`
collapses the double slash, so it cannot work.

## Read from S3

The `s3:` handler needs boto3, which is an optional extra:

```bash
pip install confarg[s3]
```

```python
cfg = confarg.load(AppConfig, files=["s3://my-bucket/env/prod.yaml"])
```

Credentials come from boto3's ordinary chain — environment variables, a shared credentials file,
an instance or task role — so `confarg` never sees them and has no options of its own for them.

## Register a scheme of your own

`confarg.register_scheme()` takes a scheme name and a function returning the document's bytes:

```python
import confarg
from google.cloud import storage   # for example

def read_gcs(location: str) -> bytes:
    bucket_name, _, key = location.removeprefix("gs://").partition("/")
    return storage.Client().bucket(bucket_name).blob(key).download_as_bytes()

confarg.register_scheme("gs", read_gcs)

cfg = confarg.load(AppConfig, files=["gs://my-bucket/app.yaml"])
```

The handler receives the location exactly as it was written, scheme included, and returns raw
`bytes`. It never decodes: `confarg` does that itself, per format, which is what keeps a
byte-order mark working in JSON and CSV. Signal failure by raising `OSError` — the library turns
that into its own `InvalidConfigFileError`, naming the location.

Register the scheme before the `load()` or `merge()` call that needs it. Anything else
`confarg` does with a location — choosing the parser, resolving a relative `__include__`,
detecting an include cycle — a handler is not asked about and cannot change.

### Add authentication, a timeout, or caching

Registering a name that already exists replaces it, which is the intended way to change how a
built-in scheme behaves. The built-in `http`/`https` handler is a plain `urlopen` with a ten
second timeout and no authentication; when you need more, supply your own:

```python
import urllib.request

TOKEN = "..."

def read_authenticated(location: str) -> bytes:
    request = urllib.request.Request(location, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()

confarg.register_scheme("https", read_authenticated)
```

Caching works the same way. `confarg` does not cache: a root `--config` location is read twice
per run, once by the pass that discovers class tags and once by the pipeline, exactly as a local
file is. If those two fetches matter, wrap the built-in behaviour:

```python
import functools

from confarg._sources import _read_http   # the built-in, to delegate to

confarg.register_scheme("https", functools.cache(_read_http))
```

### Forbid a scheme entirely

`confarg.unregister_scheme()` removes a reader, the built-in ones included. A location naming
the scheme afterwards is refused the way any unknown scheme is, and because the registry is
global that holds for every channel at once. Removing `http` and `https` is therefore how a
program states that its configuration never comes off the network, whatever a `--config`
argument or an environment variable asks for:

```python
import confarg

confarg.unregister_scheme("http")
confarg.unregister_scheme("https")

# Raises InvalidConfigFileError, and so does --config or CONFIG naming the same URL.
confarg.load(AppConfig, files=["https://cfg.example.com/app.yaml"])
```

Do it once at start-up, before any `load()` or `merge()`. Removing a scheme that is not
registered raises `ValueError` rather than passing silently: the usual cause is a misspelled
name, and a silent no-op would leave that scheme loadable while looking as though it had been
taken away. To *change* a handler rather than remove one, pass the new reader to
`register_scheme()` — it overwrites in place, so there is nothing to unregister first.


## Relative includes inside a fetched document

A relative `__include__` in a document fetched over a URL resolves against that document's own
location, so a set of files keeps working when you move it from a directory to a bucket:

```yaml
# https://cfg.example.com/env/prod.yaml
__include__: ../base.yaml       # -> https://cfg.example.com/base.yaml
database:
  __include__: ./db.yaml        # -> https://cfg.example.com/env/db.yaml
```

A fetched document can only reach **its own scheme and host**. These are all refused:

```yaml
# https://cfg.example.com/app.yaml
__include__: /etc/passwd                              # refused: a local path
__include__: file:///etc/shadow                       # refused: another scheme
__include__: https://internal.example.com/secrets.yaml  # refused: another host
```

The reason is that the location itself is often not trusted — it can come from a `--config`
argument or an environment variable — and without the rule any config URL would double as a way
to read local files and probe an internal network. A local file has no such restriction: it may
include any location, because whoever wrote it is whoever runs the program.

## Where this stops

* **The format comes from the extension**, after any query string is stripped:
  `https://h/app.yaml?env=prod` is YAML. A location with no extension cannot be loaded — nothing
  looks at the content or at a `Content-Type` header. An endpoint that serves configuration must
  therefore have a path ending in `.yaml`, `.yml`, `.toml` or `.json`.
* **Reading only.** `dump_file()` writes to the filesystem; there is no way to write a
  configuration back to a URL.
* **No retries and no error recovery.** A location that cannot be read fails the load. If a
  remote source is optional, or should fall back to a local copy, do that in your own handler.
* **A relative filename containing a colon** in its first segment — `weird:name.yaml` — reads as
  a scheme. Write it `./weird:name.yaml`.
* **A `file://` URL is local only.** A host other than `localhost` is refused rather than
  silently reinterpreted, and translation to a path is platform-dependent.

## Which one

| You want | Use |
|---|---|
| A config file next to the program | a plain path |
| One canonical config served to many machines | `https://…`, with your own handler if it needs a token |
| Config versioned in an object store | `s3://…` (`pip install confarg[s3]`) |
| A store `confarg` does not know | `confarg.register_scheme()` |
| A path spelled as a URL, for uniformity | `file://…` |
| No configuration off the network, ever | `confarg.unregister_scheme()` for `http`/`https` |
