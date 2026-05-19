"""Ready-made Execute-mode task templates.

Each ``.json`` file in this directory describes a common desktop task with
named variables. Users can run one as:

    lucid exec --template send_gmail --var to=x@y.com --var subject=hi

``load_template`` returns the expanded prompt string that gets handed to
:class:`lucid.agent.execute_mode.ExecuteMode`.
"""

from lucid.templates.loader import (
    TemplateError,
    TemplateSpec,
    expand_template,
    list_templates,
    load_template,
)

__all__ = [
    "TemplateError",
    "TemplateSpec",
    "expand_template",
    "list_templates",
    "load_template",
]
