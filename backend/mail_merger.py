import re


def merge(template: str, data: dict) -> str:
    """Replace {key} placeholders with values from data dict."""

    def replace(match):
        key = match.group(1)
        return str(data.get(key, match.group(0)))

    return re.sub(r"\{(\w+)\}", replace, template)


def preview_emails(rows: list, subject_tpl: str, body_tpl: str, count: int = 5):
    """Generate preview list of merged subjects/bodies."""
    previews = []
    for row in rows[:count]:
        previews.append(
            {
                "email": row.get("email", ""),
                "name": row.get("name", ""),
                "subject": merge(subject_tpl, row),
                "body": merge(body_tpl, row),
            }
        )
    return previews
