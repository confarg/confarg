from collections.abc import Callable


def count_labels(path: str) -> int:
    with open(path) as file:
        return sum(1 for line in file if line.strip())


class Annotations:
    def __init__(self, path: str) -> None:
        with open(path) as file:
            self.labels = [line.strip() for line in file if line.strip()]

    def count(self, *, unique: bool = False) -> int:
        return len(set(self.labels)) if unique else len(self.labels)


def make_tokenizer(stopwords: str) -> Callable[[str], list[str]]:
    with open(stopwords) as file:
        ignored = set(file.read().split())

    def tokenize(text: str) -> list[str]:
        return [word for word in text.split() if word not in ignored]

    return tokenize
