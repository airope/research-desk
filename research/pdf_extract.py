"""Isolated PDF parsing worker. Input: PDF bytes; output: bounded JSON evidence."""

import io
import json
import sys

MAX_PAGES = 40
MAX_PAGE_CHARS = 15000
MAX_TOTAL_CHARS = 150000
MAX_BYTES = 15 * 1024 * 1024


def extraction_limits():
    # Resource support varies by OS; wall time is additionally enforced by the parent.
    try:
        import resource

        for kind, limit in ((resource.RLIMIT_CPU, 20), (resource.RLIMIT_AS, 768 * 1024 * 1024)):
            try:
                resource.setrlimit(kind, (limit, limit))
            except (ValueError, OSError):
                pass
    except ImportError:
        pass


def extract_pages(reader):
    total = len(reader.pages)
    pages = []
    remaining = MAX_TOTAL_CHARS
    truncated = total > MAX_PAGES
    for index in range(min(total, MAX_PAGES)):
        if remaining <= 0:
            truncated = True
            break
        text = " ".join((reader.pages[index].extract_text() or "").split())
        allowed = min(MAX_PAGE_CHARS, remaining)
        if len(text) > allowed:
            truncated = True
            text = text[:allowed]
        pages.append({"page": index + 1, "text": text})
        remaining -= len(text)
    return {"pages": pages, "total_pages": total, "truncated": truncated}


def main():
    extraction_limits()
    from pypdf import PdfReader

    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return 1
    try:
        result = extract_pages(PdfReader(io.BytesIO(data)))
    except Exception:
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
