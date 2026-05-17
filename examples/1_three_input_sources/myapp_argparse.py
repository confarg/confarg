from configs import PostgreSQLConfig

import confarg.cli.argparse as confparse


def main() -> None:
    """Load and print the configuration."""
    parser = confparse.make_parser(PostgreSQLConfig)
    options = parser.parse_args()
    config = confparse.from_namespace(PostgreSQLConfig, options, env_prefix="MYAPP_")
    print(config)


if __name__ == "__main__":
    main()
