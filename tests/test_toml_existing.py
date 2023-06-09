import datetime as dt
import math
import tomllib
import typing
from pathlib import Path
from pprint import pprint

import pytest

import src.typedconfig as typedconfig
from src.typedconfig.errors import ConfigError

from .constants import _load_toml, EMPTY_FILE, EXAMPLE_FILE


def test_example_is_valid_toml():
    data = _load_toml()

    assert data


class AbsHasName:
    # can be inherited by other classes with a 'name' attribute.
    name: str


# class FirstExtraName:
#     first: str
#     last: str
#
#
# class FirstExtraPoint:
#     x: int
#     y: int
#
#
# class FirstExtraAnimalType(AbsHasName):
#     ...
#
#
# class FirstExtraAnimal:
#     type: FirstExtraAnimalType
#
#
# class FirstExtra:
#     name: FirstExtraName
#     point: FirstExtraPoint
#     animal: FirstExtraAnimal


class First:
    string: str
    list_of_string: list[str]
    list_of_int: list[int]
    list_of_float: list[float]
    list_of_numbers: list[float | int]
    some_boolean: bool
    number: float | int
    not_a_number: math.nan
    datetime: dt.datetime
    datetimes: list[dt.datetime]
    extra: typing.Optional[dict[str, typing.Any]]


class FruitDetails:
    color: str
    shape: str


class FruitVariety(AbsHasName):
    ...


class Fruit(AbsHasName):
    varieties: list[FruitVariety]
    physical: typing.Optional[FruitDetails]


class SecondExtra:
    allowed: bool


class Tool:
    first: First
    fruits: list[Fruit]
    second_extra: SecondExtra


class ToolWithInit(Tool):
    more_props: str

    def __init__(self, more_properties: str):
        self.more_props = more_properties


def test_new_instances():
    data = _load_toml()

    tool = typedconfig.load_into(ToolWithInit, data, init=dict(more_properties="more kwargs"))
    assert tool.more_props == "more kwargs"
    assert tool.fruits


def test_existing_instances():
    data = _load_toml()

    inst1 = ToolWithInit("some setup")

    normal_tool = typedconfig.load_into(Tool, data)
    inst1_extended = typedconfig.load_into(inst1, data)

    assert inst1.fruits

    assert inst1_extended.first.extra["name"]["first"] == normal_tool.first.extra["name"]["first"]

    with pytest.raises(ValueError):
        typedconfig.load_into(inst1, data, init=dict(more_properties="Should not be allowed!"))
