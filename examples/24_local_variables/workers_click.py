"""Example: a local variable's type comes from its declaration."""

from dataclasses import dataclass

import click

import confarg.cli.click as confargclick


@dataclass
class Config:
    """Worker pool sizing, derived from a declared CPU count."""

    workers: int
    reserved: int


@click.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Load configuration and print it."""
    print(confargclick.from_context(Config, ctx))


confargclick.populate_command(Config, run, env_prefix="MYAPP_")

if __name__ == "__main__":
    run()
