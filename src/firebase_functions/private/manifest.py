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
"""Specs for the served functions.yaml of the user's functions"""

# We're ignoring pylint's warning about names since we want
# the manifest to match the container specification.
# pylint: disable=invalid-name

import dataclasses as _dataclasses
import typing as _typing
import typing_extensions as _typing_extensions

import firebase_functions.params as _params
import firebase_functions.private.util as _util
from enum import Enum as _Enum


class SecretEnvironmentVariable(_typing.TypedDict):
    key: _typing_extensions.Required[str]
    secret: _typing_extensions.NotRequired[str]


class HttpsTrigger(_typing.TypedDict):
    """
    Trigger definition for arbitrary HTTPS endpoints.
    """

    invoker: _typing_extensions.NotRequired[list[str]]
    """
    Which service account should be able to trigger this function. No value means "make public"
    on create and don't do anything on update.
    """


class CallableTrigger(_typing.TypedDict):
    """
    Trigger definitions for RPCs servers using the HTTP protocol defined at
    https://firebase.google.com/docs/functions/callable-reference
    """


class EventTrigger(_typing.TypedDict):
    """
    Trigger definitions for endpoints that listen to CloudEvents emitted by
    other systems (or legacy Google events for GCF gen 1)
    """
    eventFilters: _typing_extensions.NotRequired[dict[str, str |
                                                      _params.Expression[str]]]
    eventFilterPathPatterns: _typing_extensions.NotRequired[dict[
        str, str | _params.Expression[str]]]
    channel: _typing_extensions.NotRequired[str]
    eventType: _typing_extensions.Required[str]
    retry: _typing_extensions.Required[bool | _params.Expression[bool]]


class RetryConfig(_typing.TypedDict):
    retryCount: _typing_extensions.NotRequired[int | _params.Expression[int]]
    maxRetrySeconds: _typing_extensions.NotRequired[str |
                                                    _params.Expression[str]]
    minBackoffSeconds: _typing_extensions.NotRequired[str |
                                                      _params.Expression[str]]
    maxBackoffSeconds: _typing_extensions.NotRequired[str |
                                                      _params.Expression[str]]
    maxDoublings: _typing_extensions.NotRequired[int | _params.Expression[int]]


class ScheduleTrigger(_typing.TypedDict):
    schedule: _typing_extensions.NotRequired[str | _params.Expression[str]]
    timeZone: _typing_extensions.NotRequired[str | _params.Expression[str]]
    retryConfig: _typing_extensions.NotRequired[RetryConfig]


class BlockingTrigger(_typing.TypedDict):
    eventType: _typing_extensions.Required[str]


class VpcSettings(_typing.TypedDict):
    connector: _typing_extensions.Required[str]
    egressSettings: _typing_extensions.NotRequired[str | _util.Sentinel]


@_dataclasses.dataclass(frozen=True)
class ManifestEndpoint:
    """A definition of a function as appears in the Manifest."""

    entryPoint: _typing.Optional[str] = None
    region: _typing.Optional[list[str]] = _dataclasses.field(
        default_factory=list[str])
    platform: _typing.Optional[str] = "gcfv2"
    availableMemoryMb: int | _params.Expression[
        int] | _util.Sentinel | None = None
    maxInstances: int | _params.Expression[int] | _util.Sentinel | None = None
    minInstances: int | _params.Expression[int] | _util.Sentinel | None = None
    concurrency: int | _params.Expression[int] | _util.Sentinel | None = None
    serviceAccountEmail: _typing.Optional[str | _util.Sentinel] = None
    timeoutSeconds: int | _params.Expression[int] | _util.Sentinel | None = None
    cpu: int | str | _util.Sentinel | None = None
    vpc: _typing.Optional[VpcSettings] = None
    labels: _typing.Optional[dict[str, str]] = None
    ingressSettings: _typing.Optional[str] | _util.Sentinel = None
    secretEnvironmentVariables: _typing.Optional[
        list[SecretEnvironmentVariable] | _util.Sentinel] = _dataclasses.field(
            default_factory=list[SecretEnvironmentVariable])
    httpsTrigger: _typing.Optional[HttpsTrigger] = None
    callableTrigger: _typing.Optional[CallableTrigger] = None
    eventTrigger: _typing.Optional[EventTrigger] = None
    scheduleTrigger: _typing.Optional[ScheduleTrigger] = None
    blockingTrigger: _typing.Optional[BlockingTrigger] = None


class ManifestRequiredApi(_typing.TypedDict):
    api: _typing_extensions.Required[str]
    reason: _typing_extensions.Required[str]


@_dataclasses.dataclass(frozen=True)
class ManifestStack:
    endpoints: dict[str, ManifestEndpoint]
    specVersion: str = "v1alpha1"
    params: list[_typing.Any] | None = _dataclasses.field(
        default_factory=list[_typing.Any])
    requiredAPIs: list[ManifestRequiredApi] = _dataclasses.field(
        default_factory=list[ManifestRequiredApi])


def _param_to_spec(
        param: _params.Param | _params.SecretParam) -> dict[str, _typing.Any]:
    spec_dict: dict[str, _typing.Any] = {
        "name": param.name,
        "label": param.label,
        "description": param.description,
        "immutable": param.immutable,
    }

    if isinstance(param, _params.Param):
        spec_dict["default"] = param.default
        # TODO spec representation of inputs

    if isinstance(param, _params.BoolParam):
        spec_dict["type"] = "boolean"
    elif isinstance(param, _params.IntParam):
        spec_dict["type"] = "int"
    elif isinstance(param, _params.FloatParam):
        spec_dict["type"] = "float"
    elif isinstance(param, _params.SecretParam):
        spec_dict["type"] = "secret"
    elif isinstance(param, _params.ListParam):
        spec_dict["type"] = "list"
        if spec_dict["default"] is not None:
            spec_dict["default"] = ",".join(spec_dict["default"])
    elif isinstance(param, _params.StringParam):
        spec_dict["type"] = "string"
    else:
        raise NotImplementedError("Unsupported param type.")

    return _dict_to_spec(spec_dict)


def _object_to_spec(data) -> object:
    if isinstance(data, _Enum):
        return data.value
    elif isinstance(data, _params.Expression):
        return data.to_cel()
    elif _dataclasses.is_dataclass(data):
        return _dataclass_to_spec(data)
    elif isinstance(data, list):
        return list(map(_object_to_spec, data))
    elif isinstance(data, dict):
        return _dict_to_spec(data)
    else:
        return data


def _dict_factory(data: list[_typing.Tuple[str, _typing.Any]]) -> dict:
    out: dict = {}
    for key, value in data:
        if value is not None:
            out[key] = _object_to_spec(value)
    return out


def _dataclass_to_spec(data) -> dict:
    out: dict = {}
    for field in _dataclasses.fields(data):
        value = _object_to_spec(getattr(data, field.name))
        if value is not None:
            out[field.name] = value
    return out


def _dict_to_spec(data: dict) -> dict:
    return _dict_factory(list(data.items()))


def manifest_to_spec_dict(manifest: ManifestStack) -> dict:
    params = manifest.params
    out: dict = _dataclass_to_spec(manifest)
    if params is not None:
        out["params"] = list(map(_param_to_spec, params))
    return out
