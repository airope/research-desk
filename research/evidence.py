"""Locate quoted abstract spans for escaped, display-only highlighting."""


def passages(abstract, report, paper_id, page=0):
    if not abstract:
        return []
    spans = []
    for row in report.get("findings", []) + report.get("comparison", []):
        for source in row.get("evidence", []):
            if source.get("paper_id") != paper_id or source.get("page", 0) != page:
                continue
            quote = " ".join(source.get("quote", "").split())
            start = abstract.find(quote) if quote else -1
            if start >= 0:
                spans.append((start, start + len(quote)))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    result, cursor = [], 0
    for start, end in merged:
        result.extend(
            [
                {"text": abstract[cursor:start], "quoted": False},
                {"text": abstract[start:end], "quoted": True},
            ]
        )
        cursor = end
    result.append({"text": abstract[cursor:], "quoted": False})
    return result
