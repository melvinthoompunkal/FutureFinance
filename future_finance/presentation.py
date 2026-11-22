from html import escape
import re

QUANTITY = re.compile(r"([+−-]?)(\$?)([+−-]?\d+(?:[.,]\d+)*)([%×KMB]| bp| pp)?(.*)")


def quantity_html(value: str) -> str:
    parts = QUANTITY.fullmatch(value)
    if not parts:
        return escape(value)
    sign, prefix, number, suffix, rest = parts.groups()
    currency = f'<span class="ff-unit">{prefix}</span>' if prefix else ""
    unit = f'<span class="ff-unit">{suffix}</span>' if suffix else ""
    return f"{sign}{currency}{number}{unit}{escape(rest)}"


def quantity_markdown(value: str) -> str:
    parts = QUANTITY.fullmatch(value)
    if not parts:
        return value
    sign, prefix, number, suffix, rest = parts.groups()
    currency = f":gray[{prefix}]" if prefix else ""
    unit = ""
    if suffix:
        space = " " if suffix.startswith(" ") else ""
        unit = f"{space}:gray[{suffix.strip()}]"
    return f"{sign}{currency}{number}{unit}{rest}"
