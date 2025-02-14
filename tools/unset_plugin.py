# SPDX-FileCopyrightText: Magenta ApS <https://magenta.dk>
# SPDX-License-Identifier: MPL-2.0
import ast
from importlib.metadata import version

from ariadne_codegen.plugins.base import Plugin
from graphql import GraphQLInputField
from graphql import Undefined

# This plugin probably doesn't work on pydantic v2 / new ariadne.
assert version("ariadne-codegen") == "0.7.1"


class UnsetInputTypesPlugin(Plugin):
    def generate_inputs_module(self, module: ast.Module) -> ast.Module:
        unset_imports = [
            ast.ImportFrom(
                level=1, module="base_model", names=[ast.alias("UnsetType")]
            ),
            ast.ImportFrom(level=1, module="base_model", names=[ast.alias("UNSET")]),
        ]

        module.body = unset_imports + module.body
        return module

    def generate_input_field(
        self,
        field_implementation: ast.AnnAssign,
        input_field: GraphQLInputField,
        field_name: str,
    ) -> ast.AnnAssign:
        if input_field.default_value != Undefined:
            return field_implementation
        if field_implementation.value is not None:
            # TODO: Actually handle this one field
            return field_implementation

        new_annotation: ast.expr
        # Handle text wrapped types, like `a: "MyTypeHere"`
        if (
            isinstance(field_implementation.annotation, ast.Name)
            and '"' in field_implementation.annotation.id
        ):
            new_annotation = ast.Name(
                '"'
                + field_implementation.annotation.id.strip('"')
                + " | UnsetType"
                + '"'
            )
        else:  # Handle all other types
            new_annotation = ast.BinOp(
                left=field_implementation.annotation,
                op=ast.BitOr(),
                right=ast.Name("UnsetType"),
            )

        return ast.AnnAssign(
            target=field_implementation.target,
            annotation=new_annotation,
            value=ast.Name("UNSET"),
            simple=field_implementation.simple,
        )
