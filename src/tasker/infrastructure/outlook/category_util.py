"""Semicolon-delimited category strings (Outlook ``MailItem.Categories``)."""


def merge_category_strings(existing: str, addition: str) -> str:
    """Merge two category strings; order preserved, case-sensitive de-dup on strips."""
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in (existing or "").split(";"):
        s = chunk.strip()
        if s and s not in seen:
            seen.add(s)
            parts.append(s)
    for chunk in (addition or "").split(";"):
        s = chunk.strip()
        if s and s not in seen:
            seen.add(s)
            parts.append(s)
    return "; ".join(parts)
