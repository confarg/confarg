# Local variables

> [!TIP]
> Code for examples on this page can be found in [`examples/23_local_variables`](https://github.com/confarg/confarg/tree/master/examples/23_local_variables).

Sometimes, different parts of a configuration share some common values. This can happen when you are working with a broad configuration that you want to narrow down in your own use case. For example, the configuration could take a list of base class objects, and in your scenario, you use derived classes that share some common parameter. Or the configuration allows you to choose log and output directories at your will, but you actually want those directories to be derived from a base output directory.

You don't want to copy-paste dependent values in your configuration files. At the same time, you don't want to add extra parameters in your app's configuration for this sole purpose. This could bake in some contextual dependencies that fit your needs but harm the flexibility of the configuration, as in the shared base directory example. Maybe you cannot touch the configuration at all as you don't own it.

For such situations, confarg introduces custom scratch spaces in configuration files where new variables, unknown to the configuration, can be declared. This scratch space can be created using the reserved `locals:` block at the root of a configuration file.

To illustrate this, let's take this configuration.

<!-- snippet: paths.py#Config -->
```python
@dataclass
class Config:
    output_dir: str
    log_dir: str
```

You can write a custom configuration that mutualizes a base dir value like so:

<!-- snippet: paths.yaml -->
```yaml title="paths.yaml"
locals:
  base_dir: /srv/myapp

output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console

The local variable in the config file can be modified from the environment on from the CLI, offering a new configuration handle to the user, tailored to your use case, that the target configuration does not have to know about.
$ uv run paths.py --config paths.yaml
Config(output_dir='/srv/myapp/output', log_dir='/srv/myapp/logs')
```


```console
$ # Change the app's base directory -- a concept the config doesn't know about
$ uv run paths.py --config paths.yaml --locals.base_dir /home/bob
Config(output_dir='/home/bob/output', log_dir='/home/bob/logs')
```


The environment does the same, following the usual naming rules:

<!-- pytest-markdown-console: platform:linux -->
```console
$ MYAPP_LOCALS__BASE_DIR=/home/bob uv run paths.py --config paths.yaml
Config(output_dir='/home/bob/output', log_dir='/home/bob/logs')
```

Note that the `locals:` block is a standard block. Local variables can be nested and of any type, which can be used to organize them at your will.

<!-- snippet: nested_locals.yaml -->
```yaml title="nested_locals.yaml"
locals:
  dirs:
    base: /srv/myapp

output_dir: ${locals.dirs.base}/output
log_dir: ${locals.dirs.base}/logs
```

```console
$ uv run paths.py --config nested_locals.yaml
Config(output_dir='/srv/myapp/output', log_dir='/srv/myapp/logs')
```


## Expressions

A local variable may be an expression, including one over another local variable.

<!-- snippet: derived_locals.yaml -->
```yaml title="derived_locals.yaml"
locals:
  root_dir: /srv
  base_dir: ${locals.root_dir}/myapp

output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console
$ uv run paths.py --config derived_locals.yaml
Config(output_dir='/srv/myapp/output', log_dir='/srv/myapp/logs')
```


A local may also be an expression over an ordinary field. In this scenario for example, we use it to set a default value for our `base_dir` handle that relies on the deploy environment.

<!-- snippet: deploy.py#Config -->
```python
@dataclass
class Config:
    deploy_env: str
    output_dir: str
    log_dir: str
```

<!-- snippet: deploy_paths.yaml -->
```yaml title="deploy_paths.yaml"
locals:
  base_dir: /srv/${deploy_env}

deploy_env: dev
output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console
$ uv run deploy.py --config deploy_paths.yaml
Config(deploy_env='dev', output_dir='/srv/dev/output', log_dir='/srv/dev/logs')
$ uv run deploy.py --config deploy_paths.yaml --deploy_env prod
Config(deploy_env='prod', output_dir='/srv/prod/output', log_dir='/srv/prod/logs')
```


## Sharing variables between configurations

The `locals:` block is an ordinary block, so [`__include__`](https://confarg.github.io/confarg/examples/11_include/) works inside it.

<!-- snippet: vars.yaml -->
```yaml title="vars.yaml"
base_dir: /mnt/shared/myapp
```

<!-- snippet: included_locals.yaml -->
```yaml title="included_locals.yaml"
locals:
  __include__: ./vars.yaml

output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console
$ uv run paths.py --config included_locals.yaml
Config(output_dir='/mnt/shared/myapp/output', log_dir='/mnt/shared/myapp/logs')
```


This would work similarly from the command-line arguments:

```console
$ uv run paths.py --config paths.yaml --config.locals vars.yaml
Config(output_dir='/mnt/shared/myapp/output', log_dir='/mnt/shared/myapp/logs')
```


## Local variable type

A local has no annotation, so its type is whatever declared it in a configuration file, which is one of the scalar types. Once declared, the type is fixed, and an override is converted to it:

<!-- snippet: workers.yaml -->
```yaml title="workers.yaml"
locals:
  cpus: 4

workers: ${locals.cpus * 2}
reserved: ${locals.cpus}
```

```console
$ uv run workers.py --config workers.yaml
Config(workers=8, reserved=4)
$ uv run workers.py --config workers.yaml --locals.cpus 8
Config(workers=16, reserved=8)
$ # Error: 'cpus' is declared as an integer
$ uv run workers.py --config workers.yaml --locals.cpus many
...
```


## From outside configuration files

The environment and command-line parameters cannot create local variables.

```console
$ # Error: 'bse' was never declared
$ uv run paths.py --config paths.yaml --locals.bse /home/bob
...
```


However, existing local variables declared in configuration files can be accessed and modified from there, as we have seen above: they make great custom configuration handles.

## Alternative name

`locals` is a built-in function in Python and would typically not be chosen as a configuration key. However, if such a case arises, the `_locals` keyword can be used interchangeably.

<!-- snippet: underscore_locals.yaml -->
```yaml title="underscore_locals.yaml"
_locals:
  base_dir: /srv/myapp

output_dir: ${_locals.base_dir}/output
log_dir: ${_locals.base_dir}/logs
```

```console
$ uv run paths.py --config underscore_locals.yaml --_locals.base_dir /home/bob
Config(output_dir='/home/bob/output', log_dir='/home/bob/logs')
```
