from dataclasses import dataclass


@dataclass
class APIConfig:
    url: str
    token: str
