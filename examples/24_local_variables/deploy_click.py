"""Example: deriving a local variable from a real, overridable field."""

from dataclasses import dataclass

import click

import confarg.cli.click as confargclick


@dataclass
class Config:
    """Paths scoped to a deployment environment."""

    deploy_env: str
    output_dir: str
    log_dir: str


@click.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Load configuration and print it."""
    print(confargclick.from_context(Config, ctx))


confargclick.populate_command(Config, run, env_prefix="MYAPP_")

if __name__ == "__main__":
    run()
