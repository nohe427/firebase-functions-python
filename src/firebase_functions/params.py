# Copyright 2022 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Module for params that can make Cloud Functions codebases generic."""

import abc as _abc
import dataclasses as _dataclasses
import os as _os
import re as _re
import typing as _typing

_T = _typing.TypeVar("_T", str, int, float, bool, list)


@_dataclasses.dataclass(frozen=True)
class Expression(_abc.ABC, _typing.Generic[_T]):
    """
    A CEL expression which can be evaluated during function deployment, and
    resolved to a value of the generic type parameter: i.e, you can pass
    an Expression<number> as the value of an option that normally accepts numbers.
    """

    def value(self) -> _T:
        """
        Returns the Expression's runtime value, based on the CLI's resolution of params.
        """
        raise NotImplementedError()

    def to_cel(self) -> str:
        """
        Returns the Expression's representation as a braced CEL expression.
        """
        return f"{{{{ {self} }}}}"


def _quote_if_string(literal: _T) -> _T:
    return literal if not isinstance(literal, str) else f'"{literal}"'


_params: dict[str, Expression] = {}


@_dataclasses.dataclass(frozen=True)
class TernaryExpression(Expression[_T], _typing.Generic[_T]):
    test: Expression[bool]
    if_true: _T
    if_false: _T

    def value(self) -> _T:
        return self.if_true if self.test.value() else self.if_false

    def __str__(self) -> str:
        return f"{self.test} ? {_quote_if_string(self.if_true)} : {_quote_if_string(self.if_false)}"


@_dataclasses.dataclass(frozen=True)
class CompareExpression(Expression[bool], _typing.Generic[_T]):
    """
    A CEL expression that evaluates to boolean true or false based on a comparison
    between the value of another expression and a literal of that same type.
    """
    comparator: str
    left: Expression[_T]
    right: _T

    def value(self) -> bool:
        left: _T = self.left.value()
        if self.comparator == "==":
            return left == self.right
        elif self.comparator == ">":
            return left > self.right
        elif self.comparator == ">=":
            return left >= self.right
        elif self.comparator == "<":
            return left < self.right
        elif self.comparator == "<=":
            return left <= self.right
        else:
            raise ValueError(f"Unknown comparator {self.comparator}")

    def __str__(self) -> str:
        return f"{self.left} {self.comparator} {_quote_if_string(self.right)}"

    def then(self, if_true: _T, if_false: _T) -> TernaryExpression[_T]:
        return TernaryExpression(self, if_true, if_false)


@_dataclasses.dataclass(frozen=True)
class SelectOptions(_typing.Generic[_T]):
    """
    A representation of an option that can be selected via a SelectInput.
    """

    value: _T
    """The value of the option."""

    label: _typing.Optional[str] = None
    """The displayed label for the option."""


@_dataclasses.dataclass(frozen=True)
class SelectInput(_typing.Generic[_T]):
    """
    Specifies that a Param's value should be determined by having the user select
    from a list of pre-canned options interactively at deploy-time.
    """

    options: list[SelectOptions[_T]]
    """A list of user selectable options."""


@_dataclasses.dataclass(frozen=True)
class TextInput:
    """
    Specifies that a Param's value should be determined by prompting the user
    to type it in interactively at deploy-time. Input that does not match the provided
    validation_regex, if present, will be retried.
    """

    example: _typing.Optional[str] = None
    """
    An example of the input required that will be displayed alongside the input prompt.
    """

    validation_regex: _typing.Optional[str] = None
    """
    Validation regex for the input.
    Input that does not match this regex, if present, will be retried.
    """

    validation_error_message: _typing.Optional[str] = None
    """
    An error message that is displayed to the user if validation_regex fails.
    """


@_dataclasses.dataclass(frozen=True)
class ResourceInput:
    """
    Specifies that a Param's value should be determined by having the user
    select from a list containing all the project's resources of a certain
    type. Currently, only type:"storage.googleapis.com/Bucket" is supported.
    """

    type: str
    """
    The resource type. Currently, only type:"storage.googleapis.com/Bucket" is supported.
    """


@_dataclasses.dataclass(frozen=True)
class Param(Expression[_T]):
    """
    A param is a declared dependency on an external value.
    """

    name: str
    """
    The environment variable of this parameter. Must be upper case.
    """

    default: _typing.Optional[_T] = None
    """
    The default value to assign to this param if none provided.
    """

    label: _typing.Optional[str] = None
    """
    A label that is displayed to the user for this param.
    """

    description: _typing.Optional[str] = None
    """
    Description of this param that is displayed to the user.
    """

    immutable: _typing.Optional[bool] = None
    """
    Whether the value of this parameter can change between function
    deployments.
    """

    input: _typing.Union[TextInput, ResourceInput,
                         SelectInput[_T]] = TextInput()
    """
    The type of input that is required for this param, e.g. TextInput.
    """

    def value(self) -> _T:
        raise NotImplementedError()

    def compare(self, compare: str, right: _T) -> CompareExpression:
        return CompareExpression(compare, self, right)

    def equals(self, right: _T) -> CompareExpression:
        return self.compare("==", right)

    def __str__(self) -> str:
        return f"params.{self.name}"

    def __post_init__(self):
        if isinstance(self, _DefaultStringParam):
            return
        if not _re.match(r"^[A-Z0-9_]+$", self.name):
            raise ValueError(
                "Parameter names must only use uppercase letters, numbers and "
                "underscores, e.g. 'UPPER_SNAKE_CASE'.")
        if self.name in _params:
            raise ValueError(
                f"Duplicate Parameter Error: The parameter '{self.name}' has already been declared."
            )
        _params[self.name] = self


@_dataclasses.dataclass(frozen=True)
class SecretParam(Expression[str]):
    """
    A secret param is a declared dependency on an external secret.
    """

    name: str
    """
    The environment variable of this parameter. Must be upper case.
    """

    label: _typing.Optional[str] = None
    """
    A label that is displayed to the user for this param.
    """

    description: _typing.Optional[str] = None
    """
    Description of this param that is displayed to the user.
    """

    immutable: _typing.Optional[bool] = None
    """
    Whether the value of this parameter can change between function
    deployments.
    """

    def __str__(self):
        return f"params.{self.name}"

    def __post_init__(self):
        if not _re.match(r"^[A-Z0-9_]+$", self.name):
            raise ValueError(
                "Parameter names must only use uppercase letters, numbers and "
                "underscores, e.g. 'UPPER_SNAKE_CASE'.")
        if self.name in _params:
            raise ValueError(
                f"Duplicate Parameter Error: The parameter '{self.name}' has already been declared."
            )
        _params[self.name] = self

    def value(self) -> str:
        """Current value of this parameter."""
        return _os.environ.get(self.name, "")

    def compare(self, compare: str, right: _T) -> CompareExpression:
        return CompareExpression(compare, self, right)

    def equals(self, right: _T) -> CompareExpression:
        return self.compare("==", right)


@_dataclasses.dataclass(frozen=True)
class StringParam(Param[str]):
    """A parameter as a string value."""

    def value(self) -> str:
        if _os.environ.get(self.name) is not None:
            return _os.environ[self.name]

        if self.default is not None:
            return self.default

        return str()


@_dataclasses.dataclass(frozen=True)
class IntParam(Param[int]):
    """A parameter as a int value."""

    def value(self) -> int:
        if _os.environ.get(self.name) is not None:
            return int(_os.environ[self.name])
        if self.default is not None:
            return self.default
        return int()


@_dataclasses.dataclass(frozen=True)
class FloatParam(Param[float]):
    """A parameter as a float value."""

    def value(self) -> float:
        if _os.environ.get(self.name) is not None:
            return float(_os.environ[self.name])
        if self.default is not None:
            return self.default
        return float()


@_dataclasses.dataclass(frozen=True)
class BoolParam(Param[bool]):
    """A parameter as a bool value."""

    def value(self) -> bool:
        env_value = _os.environ.get(self.name)
        if env_value is not None:
            if env_value.lower() in ["true", "t", "1", "y", "yes"]:
                return True
            if env_value.lower() in ["false", "f", "0", "n", "no"]:
                return False
            raise ValueError(f"Invalid value for {self.name}: {env_value}")
        if self.default is not None:
            return self.default
        return False


@_dataclasses.dataclass(frozen=True)
class ListParam(Param[list]):
    """A parameter as a list of strings."""

    def value(self) -> list[str]:
        if _os.environ.get(self.name) is not None:
            return list(filter(len, _os.environ[self.name].split(",")))
        if self.default is not None:
            return self.default
        return []


@_dataclasses.dataclass(frozen=True)
class _DefaultStringParam(StringParam):
    """
    Internal use only.
    This is a parameter that is available by default in all functions.
    These are excluded from the list of parameters that are prompted to the user.
    """


PROJECT_ID = _DefaultStringParam(
    "GCLOUD_PROJECT",
    description="The active Firebase project",
)

STORAGE_BUCKET = _DefaultStringParam(
    "STORAGE_BUCKET",
    description="The default Cloud Storage for Firebase bucket",
)

DATABASE_URL = _DefaultStringParam(
    "DATABASE_URL",
    description="The Firebase project's default Realtime Database instance URL",
)

DATABASE_INSTANCE = _DefaultStringParam(
    "DATABASE_INSTANCE",
    description="The Firebase project's default Realtime Database instance name",
)

EXTENSION_ID = _DefaultStringParam(
    "EXT_INSTANCE_ID",
    label="Extension instance ID",
    description="When a function is running as part of an extension, "
    "this is the unique identifier for the installed extension "
    "instance",
    default="",
)
