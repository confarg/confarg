"""Example: a local variable's type comes from its declaration."""

from dataclasses import dataclass

import cyclopts

import confarg.cli.cyclopts as confargcyclopts


@dataclass
class Config:
    """Worker pool sizing, derived from a declared CPU count."""

    workers: int
    reserved: int


app = cyclopts.App()
confargcyclopts.populate_app(Config, app, env_prefix="MYAPP_")

if __name__ == "__main__":
    print(confargcyclopts.from_app(Config, app))
