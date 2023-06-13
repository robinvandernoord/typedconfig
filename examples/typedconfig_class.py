"""
Example with basic classes
"""

from typedconfig import load_into, TypedConfig


class AbsHasName(TypedConfig):
    name: str


class Two(AbsHasName):
    some_str: str
    some_int: int

    def __repr__(self) -> str:
        return f"{self.name=} {self.some_str=} {self.some_int=}"


class Simple(AbsHasName):
    two: Two

    def __repr__(self) -> str:
        return f"{self.name=} {self.two=}"


def main() -> None:
    data = {"simple": {"name": "Steve", "two": {"name": "Alex", "some_str": "string", "some_int": 30}}}

    simple = Simple.load(data)
    two = simple.two
    print(simple, two)


if __name__ == "__main__":
    main()
