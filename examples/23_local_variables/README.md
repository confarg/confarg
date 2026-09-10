# Local variables

> [!TIP]
> Code for examples in this page can be found in [`examples/23_local_variables`](https://github.com/confarg/confarg/tree/master/examples/23_local_variables).

Sometimes, different part of a configuration share some common values. This can happen when you are working with a broad configuration that you want to narrow down in your own use case. For example, the configuration could take a list of base class objects, and in your scenario, you use derived classes that share some common parameter. Or the configuration allows to choose log and output directories at your will, but you actually want those directories to be derived from a base output directory.

You don't want to copy-paste dependent values in your configuration files. At the same time, you don't want to add extra parameters in your app's configuration for this sole purpose. This could bake in some contextual dependencies that fits your needs but harm the flexibility of the configuration, as in the shared based directory example. Maybe you cannot touch the configuration at all as you don't own it.

For such situations, confarg introduces custom scratch spaces in configuration files where new variables, unknown to the configuration, can be declared. This scratch space can be created using the reserved `locals:` block at the root of a configuration file.

To illustrate this, let's take this configuration.

```python
@dataclass
class Config:
  output_dir: str
  log_dir: str
```

You can write a custom configuration that mutualize a base dir value like so:

```yaml
# config1.yaml
locals:
  base_dir: /srv/myapp

output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console
$ uv run paths.py --config config1.yaml
Config(output_dir='/srv/myapp/output', log_dir='/srv/myapp/logs')
```

The local variable in the config file can be modified from the environment on from the CLI, offering a new configuration handle to the user, tailored to your use case, that the target configuration does not have to know about.

```console
$ # Change the app's base directory -- a concept the config doesn't know about
$ uv run paths.py --config config1.yaml --locals.base_dir /home/bob
Config(output_dir='/home/bob/output', log_dir='/home/bob/logs')
```

The environment does the same, following the usual naming rules:

<!-- pytest-markdown-console: platform:linux -->
```console
$ MYAPP_LOCALS__BASE_DIR=/home/bob uv run paths.py --config config1.yaml
Config(output_dir='/home/bob/output', log_dir='/home/bob/logs')
```

Note that the `locals:` block is a standard block. Local variables can be nested and of any type, which can be used to organize them at your will.

```yaml
# config9.yaml
locals:
  dirs:
    base: /srv/myapp

output_dir: ${locals.dirs.base}/output
log_dir: ${locals.dirs.base}/logs
```

```console
$ uv run paths.py --config config9.yaml
Config(output_dir='/srv/myapp/output', log_dir='/srv/myapp/logs')
```



## Expressions

A local variable may be an expression, including one over another local variable.

```yaml
# config2.yaml
locals:
  root_dir: /srv
  base_dir: ${locals.root_dir}/myapp

output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console
$ uv run paths.py --config config2.yaml
Config(output_dir='/srv/myapp/output', log_dir='/srv/myapp/logs')
```


A local may also be an expression over an ordinary field. In this scenario for example, we use it to set a default value to our `base_dir` handle that relies on the deploy environment.

```python
@dataclass
class Config:
  deploy_env: str
  output_dir: str
  log_dir: str
```

```yaml
# config4.yaml
locals:
  base_dir: /srv/${deploy_env}

deploy_env: dev
output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console
$ uv run deploy.py --config config4.yaml
Config(deploy_env='dev', output_dir='/srv/dev/output', log_dir='/srv/dev/logs')
$ uv run deploy.py --config config4.yaml --deploy_env prod
Config(deploy_env='prod', output_dir='/srv/prod/output', log_dir='/srv/prod/logs')
```


## Sharing variables between configurations

The `locals:` is an ordinary block, so [`__include__`](https://confarg.github.io/confarg/examples/11_include/) works inside it.

```yaml
# vars.yaml
base_dir: /mnt/shared/myapp
```

```yaml
# config3.yaml
locals:
  __include__: ./vars.yaml

output_dir: ${locals.base_dir}/output
log_dir: ${locals.base_dir}/logs
```

```console
$ uv run paths.py --config config3.yaml
Config(output_dir='/mnt/shared/myapp/output', log_dir='/mnt/shared/myapp/logs')
```

This would work similarly from the command line arguments:

```console
$ uv run paths.py --config config1.yaml --config.locals vars.yaml
Config(output_dir='/mnt/shared/myapp/output', log_dir='/mnt/shared/myapp/logs')
```

## Local variable type

A local has no annotation, so its type is whatever declared it in a configuration file, which is one of the scalar types. Once declared, the type is fixed, and an override is converted to it:

```yaml
# config5.yaml
locals:
  cpus: 4

workers: ${locals.cpus * 2}
reserved: ${locals.cpus}
```

```console
$ uv run workers.py --config config5.yaml
Config(workers=8, reserved=4)
$ uv run workers.py --config config5.yaml --locals.cpus 8
Config(workers=16, reserved=8)
$ # Error: 'cpus' is declared as an integer
$ uv run workers.py --config config5.yaml --locals.cpus many
...
```


## From outside configuration files

The environment and command-line parameters cannot create local variables.

```console
$ # Error: 'bse' was never declared
$ uv run paths.py --config config1.yaml --locals.bse /home/bob
...
```

However, existing local variables declared in configuration files can be accessed and modified from there, as we have seen above: they make great custom configuration handles.


## Alternative name

`locals` is a built-in function in python and would typically not be chosen as a configuration key. However, if such a case arise, the `_locals` keyword can be used interchangeably.

```yaml
# config6.yaml
_locals:
  base_dir: /srv/myapp

output_dir: ${_locals.base_dir}/output
log_dir: ${_locals.base_dir}/logs
```

```console
$ uv run paths.py --config config6.yaml --_locals.base_dir /home/bob
Config(output_dir='/home/bob/output', log_dir='/home/bob/logs')
```
