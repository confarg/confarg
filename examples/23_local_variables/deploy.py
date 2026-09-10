from dataclasses import dataclass

import confarg


@dataclass
class Config:
    deploy_env: str
    output_dir: str
    log_dir: str


def main() -> None:
    print(confarg.load(Config, env_prefix="MYAPP_"))


if __name__ == "__main__":
    main()
