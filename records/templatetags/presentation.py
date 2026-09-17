"""Display formatting only: source data and matching inputs remain unchanged."""

import json
import re
from html.parser import HTMLParser
from urllib.parse import quote

from django import template

register = template.Library()


@register.filter
def readable(value):
    labels = {
        "crossref": "Crossref",
        "openalex": "OpenAlex",
        "review": "Ready for review",
        "needs_reassessment": "Reassess",
        "insufficient_evidence": "Insufficient evidence",
        "weak_identifier": "DOI-derived",
        "doi": "DOI",
        "title_similarity": "Title similarity",
        "author_similarity": "Author similarity",
        "different_doi": "Different DOI values",
        "different_type": "Different publication types",
        "doi_title_conflict": "Same DOI, conflicting titles",
        "negation_differs": "Title negation differs",
        "numbers_differ": "Title numbers differ",
        "dates_differ": "Publication dates differ",
        "published-print": "Print",
        "published-online": "Online",
        "publication_date": "Publication",
    }
    return labels.get(str(value), str(value).replace("_", " ").capitalize())


def _math_operand(text):
    text = text.strip()
    return text if re.fullmatch(r"[-+−]?[\w.]+", text) else f"({text})"


class _TitleParser(HTMLParser):
    """Limited display-only MathML conversion; never produces trusted HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = [("root", [])]

    def handle_starttag(self, tag, attrs):
        tag = tag.rsplit(":", 1)[-1].lower()
        if tag in {"br", "hr"}:
            self.stack[-1][1].append(" ")
        elif tag not in {"img", "input", "meta", "link", "wbr"}:
            self.stack.append((tag, []))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        self.stack[-1][1].append(data)

    def handle_endtag(self, tag):
        tag = tag.rsplit(":", 1)[-1].lower()
        matches = [i for i, (name, _) in enumerate(self.stack) if name == tag and i]
        if not matches:
            return
        while len(self.stack) > matches[-1]:
            self._close_node()

    def _close_node(self):
        tag, parts = self.stack.pop()
        children = [part.strip() for part in parts if part.strip()]
        text = "".join(parts)
        if tag in {"script", "style"}:
            text = ""
        elif tag == "msqrt":
            text = "sqrt(" + "".join(children) + ")"
        elif tag in {"msup", "msub"} and len(children) >= 2:
            text = (
                children[0] + ("^" if tag == "msup" else "_") + _math_operand("".join(children[1:]))
            )
        elif tag == "msubsup" and len(children) == 3:
            text = children[0] + "_" + _math_operand(children[1]) + "^" + _math_operand(children[2])
        elif tag == "mfrac" and len(children) == 2:
            text = "(" + children[0] + ")/(" + children[1] + ")"
        elif tag in {"sup", "sub"}:
            text = ("^" if tag == "sup" else "_") + _math_operand("".join(children))
        elif tag in {"math", "p", "div"}:
            text = " " + text + " "
        self.stack[-1][1].append(text)

    def plain(self):
        while len(self.stack) > 1:
            self._close_node()
        return " ".join("".join(self.stack[0][1]).split())


@register.filter
def plain_title(value):
    parser = _TitleParser()
    parser.feed(str(value or "Untitled record"))
    parser.close()
    return parser.plain()


@register.filter
def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


@register.filter
def field_value(value):
    if isinstance(value, list):
        if all(isinstance(item, dict) and "name" in item for item in value):
            return "; ".join(item["name"] for item in value)
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        entries = []
        for kind, date in value.items():
            if isinstance(date, dict) and "date-parts" in date:
                date = "; ".join(
                    "-".join(str(part) for part in parts) for parts in date["date-parts"]
                )
            entries.append(f"{readable(kind)}: {date}")
        return "\n".join(entries)
    return str(value) if value is not None else "Not provided"


@register.filter
def doi_url(value):
    from records.normalization import normalize_doi

    doi = normalize_doi(value)
    return "https://doi.org/" + quote(doi, safe="/") if doi else ""


@register.filter
def inspire_url(value):
    identifier = str(value or "")
    if re.fullmatch(r"[0-9]{1,20}", identifier):
        return "https://inspirehep.net/literature/" + identifier
    return ""
