from dataclasses import dataclass

import click

import confarg.cli.click as confargclick


@dataclass
class Box[T]:
    """A box holding one item of any type."""

    item: T


@dataclass
class Config:
    """Configuration with two boxes, each holding its own type."""

    size: Box[int]
    label: Box[str]


@click.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Load and print the configuration."""
    config = confargclick.from_context(Config, ctx)
    print(config)


confargclick.populate_command(Config, run, env_prefix="MYAPP_")

if __name__ == "__main__":
    run()
