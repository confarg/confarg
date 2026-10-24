"""Example: local variables as intermediate values for expressions."""

from dataclasses import dataclass

import cyclopts

import confarg.cli.cyclopts as confargcyclopts


@dataclass
class Config:
    """Application paths, all derived from the same base directory."""

    output_dir: str
    log_dir: str


app = cyclopts.App()
confargcyclopts.populate_app(Config, app, env_prefix="MYAPP_")

if __name__ == "__main__":
    print(confargcyclopts.from_app(Config, app))
