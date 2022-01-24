"""Plugin to enforce type hints on specific functions."""
from __future__ import annotations

from dataclasses import dataclass
import re

import astroid
from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker
from pylint.lint import PyLinter


@dataclass
class TypeHintMatch:
    """Class for pattern matching."""

    module_filter: re.Pattern
    function_name: str
    arg_types: dict[int, str]
    return_type: str | None


_MODULE_FILTERS: dict[str, re.Pattern] = {
    # init matches only in the package root (__init__.py)
    "init": re.compile(r"^homeassistant.components.\w+$"),
}

_METHOD_MATCH: list[TypeHintMatch] = [
    TypeHintMatch(
        module_filter=_MODULE_FILTERS["init"],
        function_name="setup",
        arg_types={
            0: "HomeAssistant",
            1: "ConfigType",
        },
        return_type="bool",
    ),
    TypeHintMatch(
        module_filter=_MODULE_FILTERS["init"],
        function_name="async_setup",
        arg_types={
            0: "HomeAssistant",
            1: "ConfigType",
        },
        return_type="bool",
    ),
    TypeHintMatch(
        module_filter=_MODULE_FILTERS["init"],
        function_name="async_setup_entry",
        arg_types={
            0: "HomeAssistant",
            1: "ConfigEntry",
        },
        return_type="bool",
    ),
    TypeHintMatch(
        module_filter=_MODULE_FILTERS["init"],
        function_name="async_remove_entry",
        arg_types={
            0: "HomeAssistant",
            1: "ConfigEntry",
        },
        return_type=None,
    ),
    TypeHintMatch(
        module_filter=_MODULE_FILTERS["init"],
        function_name="async_unload_entry",
        arg_types={
            0: "HomeAssistant",
            1: "ConfigEntry",
        },
        return_type="bool",
    ),
    TypeHintMatch(
        module_filter=_MODULE_FILTERS["init"],
        function_name="async_migrate_entry",
        arg_types={
            0: "HomeAssistant",
            1: "ConfigEntry",
        },
        return_type="bool",
    ),
]


def _is_valid_type(expected_type: str | None, node: astroid.NodeNG) -> bool:
    """Check the argument node against the expected type."""
    # Const occurs when the type is None
    if expected_type is None:
        return isinstance(node, astroid.Const) and node.value is None

    # Name occurs when a namespace is not used, eg. "HomeAssistant"
    if isinstance(node, astroid.Name) and node.name == expected_type:
        return True

    # Attribute occurs when a namespace is used, eg. "core.HomeAssistant"
    return isinstance(node, astroid.Attribute) and node.attrname == expected_type


def _get_all_annotations(node: astroid.FunctionDef) -> list[astroid.NodeNG | None]:
    args = node.args
    annotations: list[astroid.NodeNG | None] = (
        args.posonlyargs_annotations + args.annotations + args.kwonlyargs_annotations
    )
    if args.vararg is not None:
        annotations.append(args.varargannotation)
    if args.kwarg is not None:
        annotations.append(args.kwargannotation)
    return annotations


def _has_valid_annotations(
    annotations: list[astroid.NodeNG | None],
) -> bool:
    for annotation in annotations:
        if annotation is not None:
            return True
    return False


class HassTypeHintChecker(BaseChecker):  # type: ignore[misc]
    """Checker for setup type hints."""

    __implements__ = IAstroidChecker

    name = "hass_enforce_type_hints"
    priority = -1
    msgs = {
        "W0020": (
            "Argument %d should be of type %s",
            "hass-argument-type",
            "Used when method argument type is incorrect",
        ),
        "W0021": (
            "Return type should be %s",
            "hass-return-type",
            "Used when method return type is incorrect",
        ),
    }
    options = ()

    def __init__(self, linter: PyLinter | None = None) -> None:
        super().__init__(linter)
        self.current_package: str | None = None
        self.module: str | None = None

    def visit_module(self, node: astroid.Module) -> None:
        """Called when a Module node is visited."""
        self.module = node.name
        if node.package:
            self.current_package = node.name
        else:
            # Strip name of the current module
            self.current_package = node.name[: node.name.rfind(".")]

    def visit_functiondef(self, node: astroid.FunctionDef) -> None:
        """Called when a FunctionDef node is visited."""
        for match in _METHOD_MATCH:
            self._visit_functiondef(node, match)

    def visit_asyncfunctiondef(self, node: astroid.AsyncFunctionDef) -> None:
        """Called when an AsyncFunctionDef node is visited."""
        for match in _METHOD_MATCH:
            self._visit_functiondef(node, match)

    def _visit_functiondef(
        self, node: astroid.FunctionDef, match: TypeHintMatch
    ) -> None:
        if node.name != match.function_name:
            return
        if node.is_method():
            return
        if not match.module_filter.match(self.module):
            return

        # Check that at least one argument is annotated.
        annotations = _get_all_annotations(node)
        if node.returns is None and not _has_valid_annotations(annotations):
            return

        # Check that all arguments are correctly annotated.
        for key, expected_type in match.arg_types.items():
            if not _is_valid_type(expected_type, annotations[key]):
                self.add_message(
                    "hass-argument-type",
                    node=node.args.args[key],
                    args=(key + 1, expected_type),
                )

        # Check the return type.
        if not _is_valid_type(return_type := match.return_type, node.returns):
            self.add_message("hass-return-type", node=node, args=return_type or "None")


def register(linter: PyLinter) -> None:
    """Register the checker."""
    linter.register_checker(HassTypeHintChecker(linter))