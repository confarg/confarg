"""Example: deriving a local variable from a real, overridable field."""

from dataclasses import dataclass

import typer
from typer.main import get_command

import confarg.cli.typer as confargtyper


@dataclass
class Config:
    """Paths scoped to a deployment environment."""

    deploy_env: str
    output_dir: str
    log_dir: str


app = typer.Typer()


@app.command()
def run(ctx: typer.Context) -> None:
    """Load configuration and print it."""
    print(confargtyper.from_context(Config, ctx))


if __name__ == "__main__":
    cmd = get_command(app)
    confargtyper.populate_command(Config, cmd, env_prefix="MYAPP_")
    cmd()
