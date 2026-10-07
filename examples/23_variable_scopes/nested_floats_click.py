"""Example: using ${field.path} expressions to interpolate values across config fields."""

from dataclasses import dataclass
from pprint import pprint

import click

import confarg
import confarg.cli.click as confargclick


@dataclass
class SubConfig:
    value1: float
    value2: float


@dataclass
class Config:
    value: float
    values: SubConfig


@click.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Load configuration and print it."""
    config = confargclick.from_context(Config, ctx, env_prefix="MYAPP_")
    pprint(config)
    config_dict = confarg.merge(Config)
    confarg.dump_file(config_dict, "saved_config_uninterpolated.yaml")
    config = confarg.build(Config, config_dict)
    confarg.dump_file(config, "saved_config_interpolated.yaml")


confargclick.populate_command(Config, run)

if __name__ == "__main__":
    run()
