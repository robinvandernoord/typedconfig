"""
Contains most of the loading logic.
"""

import tomllib
import types
import typing
import warnings
from collections import ChainMap
from dataclasses import is_dataclass
from pathlib import Path

from typeguard import TypeCheckError
from typeguard import check_type as _check_type

from .errors import ConfigErrorInvalidType, ConfigErrorMissingKey
from .helpers import camel_to_snake

# T is a reusable typevar
T = typing.TypeVar("T")
# t_typelike is anything that can be type hinted
T_typelike: typing.TypeAlias = type | types.UnionType  # | typing.Union
# t_data is anything that can be fed to _load_data
T_data = str | Path | dict[str, typing.Any]
# c = a config class instance, can be any (user-defined) class
C = typing.TypeVar("C")
# type c is a config class
Type_C = typing.Type[C]


def _data_for_nested_key(key: str, raw: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """
    If a key contains a dot, traverse the raw dict until the right key was found.

    Example:
        key = some.nested.key
        raw = {"some": {"nested": {"key": {"with": "data"}}}}
        -> {"with": "data"}
    """
    parts = key.split(".")
    while parts:
        raw = raw[parts.pop(0)]

    return raw


def _guess_key(clsname: str) -> str:
    """
    If no key is manually defined for `load_into`, \
    the class' name is converted to snake_case to use as the default key.
    """
    return camel_to_snake(clsname)


def _load_data(data: T_data, key: str = None, classname: str = None) -> dict[str, typing.Any]:
    """
    Tries to load the right data from a filename/path or dict, based on a manual key or a classname.

    E.g. class Tool will be mapped to key tool.
    It also deals with nested keys (tool.extra -> {"tool": {"extra": ...}}
    """
    if isinstance(data, str):
        data = Path(data)
    if isinstance(data, Path):
        # todo: more than toml
        with data.open("rb") as f:
            data = tomllib.load(f)

    if not data:
        return {}

    if key is None:
        # try to guess key by grabbing the first one or using the class name
        if len(data) == 1:
            key = list(data.keys())[0]
        elif classname is not None:
            key = _guess_key(classname)

    if key:
        return _data_for_nested_key(key, data)
    else:
        # no key found, just return all data
        return data


def check_type(value: typing.Any, expected_type: T_typelike) -> bool:
    """
    Given a variable, check if it matches 'expected_type' (which can be a Union, parameterized generic etc.).

    Based on typeguard but this returns a boolean instead of returning the value or throwing a TypeCheckError
    """
    try:
        _check_type(value, expected_type)
        return True
    except TypeCheckError:
        return False


def ensure_types(data: dict[str, T], annotations: dict[str, type]) -> dict[str, T | None]:
    """
    Make sure all values in 'data' are in line with the ones stored in 'annotations'.

    If an annotated key in missing from data, it will be filled with None for convenience.
    """
    # custom object to use instead of None, since typing.Optional can be None!
    # cast to T to make mypy happy
    notfound = typing.cast(T, object())

    final: dict[str, T | None] = {}
    for key, _type in annotations.items():
        compare = data.get(key, notfound)
        if compare is notfound:  # pragma: nocover
            warnings.warn(
                "This should not happen since " "`load_recursive` already fills `data` " "based on `annotations`"
            )
            # skip!
            continue
        if not check_type(compare, _type):
            raise ConfigErrorInvalidType(key, value=compare, expected_type=_type)

        final[key] = compare
    return final


def convert_config(items: dict[str, T]) -> dict[str, T]:
    """
    Converts the config dict (from toml) or 'overwrites' dict in two ways.

    1. removes any items where the value is None, since in that case the default should be used;
    2. replaces '-' and '.' in keys with '_' so it can be mapped to the Config properties.
    """
    return {k.replace("-", "_").replace(".", "_"): v for k, v in items.items() if v is not None}


Type = typing.Type[typing.Any]
T_Type = typing.TypeVar("T_Type", bound=Type)


def is_builtin_type(_type: Type) -> bool:
    """
    Returns whether _type is one of the builtin types.
    """
    return _type.__module__ in ("__builtin__", "builtins")


# def is_builtin_class_instance(obj: typing.Any) -> bool:
#     return is_builtin_type(obj.__class__)


def is_from_types_or_typing(_type: Type) -> bool:
    """
    Returns whether _type is one of the stlib typing/types types.

    e.g. types.UnionType or typing.Union
    """
    return _type.__module__ in ("types", "typing")


def is_from_other_toml_supported_module(_type: Type) -> bool:
    """
    Besides builtins, toml also supports 'datetime' and 'math' types, \
    so this returns whether _type is a type from these stdlib modules.
    """
    return _type.__module__ in ("datetime", "math")


def is_parameterized(_type: Type) -> bool:
    """
    Returns whether _type is a parameterized type.

    Examples:
        list[str] -> True
        str -> False
    """
    return typing.get_origin(_type) is not None


def is_custom_class(_type: Type) -> bool:
    """
    Tries to guess if _type is a builtin or a custom (user-defined) class.

    Other logic in this module depends on knowing that.
    """
    return (
        type(_type) is type
        and not is_builtin_type(_type)
        and not is_from_other_toml_supported_module(_type)
        and not is_from_types_or_typing(_type)
    )


def is_optional(_type: Type | None) -> bool:
    """
    Tries to guess if _type could be optional.

    Examples:
        None -> True
        NoneType -> True
        typing.Union[str, None] -> True
        str | None -> True
        list[str | None] -> False
        list[str] -> False
    """
    return (
        _type is None
        or issubclass(types.NoneType, _type)
        or issubclass(types.NoneType, type(_type))  # no type  # Nonetype
        or type(None) in typing.get_args(_type)  # union with Nonetype
    )


def load_recursive(cls: Type, data: dict[str, T], annotations: dict[str, Type]) -> dict[str, T]:
    """
    For all annotations (recursively gathered from parents with `all_annotations`), \
    try to resolve the tree of annotations.

    Uses `load_into_recurse`, not itself directly.

    Example:
        class First:
            key: str

        class Second:
            other: First

        # step 1
        cls = Second
        data = {"second": {"other": {"key": "anything"}}}
        annotations: {"other": First}

        # step 1.5
        data = {"other": {"key": "anything"}
        annotations: {"other": First}

        # step 2
        cls = First
        data = {"key": "anything"}
        annotations: {"key": str}

    """
    updated = {}
    for _key, _type in annotations.items():
        if _key in data:
            value: typing.Any = data[_key]  # value can change so define it as any instead of T
            if is_parameterized(_type):
                origin = typing.get_origin(_type)
                arguments = typing.get_args(_type)
                if origin is list and arguments and is_custom_class(arguments[0]):
                    subtype = arguments[0]
                    value = [load_into_recurse(subtype, subvalue) for subvalue in value]

                elif origin is dict and arguments and is_custom_class(arguments[1]):
                    # e.g. dict[str, Point]
                    subkeytype, subvaluetype = arguments
                    # subkey(type) is not a custom class, so don't try to convert it:
                    value = {subkey: load_into_recurse(subvaluetype, subvalue) for subkey, subvalue in value.items()}
                # elif origin is dict:
                # keep data the same
                elif origin is typing.Union and arguments:
                    for arg in arguments:
                        if is_custom_class(arg):
                            value = load_into_recurse(arg, value)
                        else:
                            # print(_type, arg, value)
                            ...

                # todo: other parameterized/unions/typing.Optional

            elif is_custom_class(_type):
                # type must be C (custom class) at this point
                value = load_into_recurse(
                    # make mypy and pycharm happy by telling it _type is of type C...
                    # actually just passing _type as first arg!
                    typing.cast(Type_C[typing.Any], _type),
                    value,
                )

        elif _key in cls.__dict__:
            # property has default, use that instead.
            value = cls.__dict__[_key]
        elif is_optional(_type):
            # type is optional and not found in __dict__ -> default is None
            value = None
        else:
            # todo: exception group?
            raise ConfigErrorMissingKey(_key, cls, _type)

        updated[_key] = value

    return updated


def _all_annotations(cls: Type) -> ChainMap[str, Type]:
    """
    Returns a dictionary-like ChainMap that includes annotations for all \
    attributes defined in cls or inherited from superclasses.
    """
    return ChainMap(*(c.__annotations__ for c in getattr(cls, "__mro__", []) if "__annotations__" in c.__dict__))


def all_annotations(cls: Type, _except: typing.Iterable[str]) -> dict[str, Type]:
    """
    Wrapper around `_all_annotations` that filters away any keys in _except.

    It also flattens the ChainMap to a regular dict.
    """
    _all = _all_annotations(cls)
    return {k: v for k, v in _all.items() if k not in _except}


def _check_and_convert_data(
    cls: typing.Type[C],
    data: dict[str, typing.Any],
    _except: typing.Iterable[str],
) -> dict[str, typing.Any]:
    """
    Based on class annotations, this prepares the data for `load_into_recurse`.

    1. convert config-keys to python compatible config_keys
    2. loads custom class type annotations with the same logic (see also `load_recursive`)
    3. ensures the annotated types match the actual types after loading the config file.
    """
    annotations = all_annotations(cls, _except=_except)

    to_load = convert_config(data)
    to_load = load_recursive(cls, to_load, annotations)
    to_load = ensure_types(to_load, annotations)
    return to_load


def load_into_recurse(
    cls: typing.Type[C],
    data: dict[str, typing.Any],
    init: dict[str, typing.Any] = None,
) -> C:
    """
    Loads an instance of `cls` filled with `data`.

    Uses `load_recursive` to load any fillable annotated properties (see that method for an example).
    `init` can be used to optionally pass extra __init__ arguments. \
        NOTE: This will overwrite a config key with the same name!
    """
    if init is None:
        init = {}

    # fixme: cls.__init__ can set other keys than the name is in kwargs!!

    if is_dataclass(cls):
        to_load = _check_and_convert_data(cls, data, init.keys())
        to_load |= init  # add extra init variables (should not happen for a dataclass but whatev)

        # ensure mypy inst is an instance of the cls type (and not a fictuous `DataclassInstance`)
        inst = typing.cast(C, cls(**to_load))
    else:
        inst = cls(**init)
        to_load = _check_and_convert_data(cls, data, inst.__dict__.keys())
        inst.__dict__.update(**to_load)

    return inst


def load_into_existing(
    inst: C,
    cls: typing.Type[C],
    data: dict[str, typing.Any],
    init: dict[str, typing.Any] = None,
) -> C:
    """
    Similar to `load_into_recurse` but uses an existing instance of a class (so after __init__) \
    and thus does not support init.

    """
    if init is not None:
        raise ValueError("Can not init an existing instance!")

    existing_data = inst.__dict__

    annotations = all_annotations(cls, _except=existing_data.keys())
    to_load = convert_config(data)
    to_load = load_recursive(cls, to_load, annotations)
    to_load = ensure_types(to_load, annotations)

    inst.__dict__.update(**to_load)

    return inst


def load_into_class(
    cls: typing.Type[C],
    data: T_data,
    /,
    key: str = None,
    init: dict[str, typing.Any] = None,
) -> C:
    """
    Shortcut for _load_data + load_into_recurse.
    """
    to_load = _load_data(data, key, cls.__name__)
    return load_into_recurse(cls, to_load, init=init)


def load_into_instance(
    inst: C,
    data: T_data,
    /,
    key: str = None,
    init: dict[str, typing.Any] = None,
) -> C:
    """
    Shortcut for _load_data + load_into_existing.
    """
    cls = inst.__class__
    to_load = _load_data(data, key, cls.__name__)
    return load_into_existing(inst, cls, to_load, init=init)


def load_into(
    cls: typing.Type[C] | C,
    data: T_data,
    /,
    key: str = None,
    init: dict[str, typing.Any] = None,
) -> C:
    """
    Load your config into a class (instance).

    Args:
        cls: either a class or an existing instance of that class.
        data: can be a dictionary or a path to a file to load (as pathlib.Path or str)
        key: optional (nested) dictionary key to load data from (e.g. 'tool.su6.specific')
        init: optional data to pass to your cls' __init__ method (only if cls is not an instance already)

    """
    if not isinstance(cls, type):
        return load_into_instance(cls, data, key=key, init=init)

    # make mypy and pycharm happy by telling it cls is of type C and not just 'type'
    _cls = typing.cast(typing.Type[C], cls)
    return load_into_class(_cls, data, key=key, init=init)
