from dataclasses import dataclass

import typer
from typer.main import get_command

import confarg.cli.typer as confargtyper


@dataclass
class Box[T]:
    """A box holding one item of any type."""

    item: T


@dataclass
class Config:
    """Configuration with two boxes, each holding its own type."""

    size: Box[int]
    label: Box[str]


app = typer.Typer()


@app.command()
def run(ctx: typer.Context) -> None:
    """Load and print the configuration."""
    config = confargtyper.from_context(Config, ctx)
    print(config)


if __name__ == "__main__":
    cmd = get_command(app)
    confargtyper.populate_command(Config, cmd, env_prefix="MYAPP_")
    cmd()
