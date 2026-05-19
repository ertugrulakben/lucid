"""Minimal custom action plugin.

Once Lucid is installed, third-party packages publish entry points like::

    [project.entry-points."lucid.actions"]
    open_project = "my_pkg.lucid_actions:open_project_module"

Inside ``my_pkg/lucid_actions.py`` you would have something equivalent
to the snippet below. Importing this file is enough; the decorator
registers the action on the global registry.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from lucid.actions import register_action
from lucid.actions.registry import ActionContext, ActionError


class OpenProjectParams(BaseModel):
    name: str = Field(..., min_length=1)
    workspace: str = Field("E:/Projects")


@register_action(
    name="open_project",
    schema=OpenProjectParams,
    summary="Open a project folder by name under a known workspace root.",
    source="entry_point",
)
def open_project(_ctx: ActionContext, params: OpenProjectParams) -> str:
    target = Path(params.workspace) / params.name
    if not target.exists():
        raise ActionError(f"workspace folder not found: {target}")
    import subprocess
    import sys

    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(target)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return f"opened {target}"


if __name__ == "__main__":
    from lucid.actions import available, run

    print("registered actions:", available())
    print(run("open_project", ActionContext(), {"name": "Lucid"}))
