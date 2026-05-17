"""Example: deriving a local variable from a real, overridable field."""

from dataclasses import dataclass

import cyclopts

import confarg.cli.cyclopts as confargcyclopts


@dataclass
class Config:
    """Paths scoped to a deployment environment."""

    deploy_env: str
    output_dir: str
    log_dir: str


app = cyclopts.App()
confargcyclopts.populate_app(Config, app, env_prefix="MYAPP_")

if __name__ == "__main__":
    print(confargcyclopts.from_app(Config, app))
