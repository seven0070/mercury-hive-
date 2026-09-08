"""Defensive prompt sanitization and untrusted input encapsulation."""

import json
import re
from typing import Any

# Dangerous delimiters that could attempt prompt injection or authority override
_DANGEROUS_PATTERNS = [
    (
        re.compile(r"<\s*/?\s*untrusted_context\s*>", re.IGNORECASE),
        "[neutralized_tag:untrusted_context]",
    ),
    (
        re.compile(r"<\s*/?\s*untrusted_task_context\s*>", re.IGNORECASE),
        "[neutralized_tag:untrusted_task]",
    ),
    (
        re.compile(r"<\s*/?\s*tool_result[^>]*>", re.IGNORECASE),
        "[neutralized_tag:tool_result]",
    ),
    (
        re.compile(r"===\s*CORE AUTHORITY HIERARCHY\s*===", re.IGNORECASE),
        "--- (neutralized authority delimiter) ---",
    ),
    (re.compile(r"<\s*\|im_start\|\s*>", re.IGNORECASE), "&lt;|im_start|&gt;"),
    (re.compile(r"<\s*\|im_end\|\s*>", re.IGNORECASE), "&lt;|im_end|&gt;"),
    (re.compile(r"<\s*\|system\|\s*>", re.IGNORECASE), "&lt;|system|&gt;"),
    (re.compile(r"\[SYSTEM\]", re.IGNORECASE), "[USER_DATA]"),
]


def sanitize_untrusted_input(text: str | None, max_chars: int = 32000) -> str:
    """Neutralize control delimiters and length-bound external/untrusted input.

    Neutralizes closing delimiter escape attempts, role-switching markers,
    and authority hierarchy override markers.
    """
    if text is None:
        return ""
    sanitized = str(text)

    # Length-bounding to prevent denial-of-service or token exhaustion
    if len(sanitized) > max_chars:
        sanitized = sanitized[:max_chars] + " ... [TRUNCATED DUE TO LENGTH]"

    for pattern, replacement in _DANGEROUS_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def wrap_untrusted_task(description: str, title: str | None = None) -> str:
    """Encapsulate an untrusted task in semantic XML boundaries."""
    sanitized_desc = sanitize_untrusted_input(description)
    title_block = ""
    if title:
        sanitized_title = sanitize_untrusted_input(title)
        title_block = f"  <task_title>{sanitized_title}</task_title>\n"

    return (
        "<untrusted_context source=\"task_specification\">\n"
        f"{title_block}"
        f"  <task_description>{sanitized_desc}</task_description>\n"
        "</untrusted_context>"
    )


def wrap_tool_result(tool_name: str, result: Any) -> str:
    """Encapsulate tool output in explicit semantic XML boundaries."""
    raw_str = (
        json.dumps(result, default=str)
        if isinstance(result, (dict, list))
        else str(result)
    )

    sanitized = sanitize_untrusted_input(raw_str)
    return (
        f'<tool_result tool_name="{sanitize_untrusted_input(tool_name)}" untrusted="true">\n'
        f"{sanitized}\n"
        "</tool_result>"
    )
