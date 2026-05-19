from pathlib import Path
from typing import Optional

# Get the directory where templates live
TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_template(template_name: str) -> str:
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_name}")
    return template_path.read_text(encoding="utf-8")


def render_template(template_name: str, **kwargs) -> str:
    content = load_template(template_name)

    for key, value in kwargs.items():
        placeholder = f"{{{{ {key} }}}}"
        content = content.replace(placeholder, str(value))

    return content
