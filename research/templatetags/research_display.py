from django import template

register = template.Library()


@register.filter
def assessment(report, index):
    return report.get("reviews", {}).get(str(index), {})


@register.filter
def research_action(value):
    return {
        "search": "Search INSPIRE",
        "reference": "Follow a reference",
        "citations": "Find citing papers",
        "read_pdf": "Extract PDF text",
        "read_page": "Read a PDF page",
        "passages": "Search source passages",
        "finish": "Finish investigation",
    }.get(value, value)
