"""Parameter schemas for built-in actions.

These wrap the loosely-typed dicts the executor used to pass around.
Each schema is a Pydantic model so plugins can both validate input and
publish a JSON Schema for the model to consume.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FocusWindowParams(BaseModel):
    title: str = Field(..., min_length=1, description="Substring of the target window title.")
    case_sensitive: bool = False


class ClickElementParams(BaseModel):
    name: str = Field(..., min_length=1, description="Accessibility name substring.")
    role: Optional[str] = Field(None, description="Optional role filter (Button, MenuItem, ...).")


class TypeTextParams(BaseModel):
    text: str
    use_clipboard: bool = True


class FileDialogPasteParams(BaseModel):
    path: str = Field(..., min_length=1)
    submit: bool = True


class WaitParams(BaseModel):
    duration_ms: int = Field(500, ge=0, le=60_000)
