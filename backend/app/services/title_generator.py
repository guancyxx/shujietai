"""Session title auto-generation from user input content."""

import re


def generate_session_title(text: str | None, max_length: int = 40) -> str | None:
    """Generate a session title from user input text.

    Normalizes whitespace (strips leading/trailing, collapses internal
    whitespace and newlines into single spaces) and truncates to max_length
    Unicode codepoints.

    Returns None if the text is None or effectively empty after cleanup,
    signaling the caller to use the default fallback title.
    """
    if not text:
        return None

    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return None

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]

    return cleaned
