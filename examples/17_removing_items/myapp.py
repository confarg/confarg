from pprint import pprint

from configs.deletion import Config

import confarg


def main() -> None:
    config = confarg.load(Config, env_prefix="MYAPP_")
    pprint(config)


if __name__ == "__main__":
    main()
