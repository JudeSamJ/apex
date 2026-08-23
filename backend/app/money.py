"""Shared type for money fields on Pydantic *response* models.

Pydantic v2 serializes a bare `Decimal` field to a JSON string (e.g.
`"42.5000"`) to avoid float precision loss — correct in principle, but this
API's frontend (and its own OpenAPI-declared `number` types) treats every
amount field as a JSON number. Use `MoneyOut` instead of `Decimal` on any
response model field that holds a monetary amount; input models can keep
using `Decimal` directly since request parsing is unaffected either way.
"""
from decimal import Decimal
from typing import Annotated
from pydantic import PlainSerializer

MoneyOut = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
