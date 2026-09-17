from django.template import Context, Template
from django.utils.safestring import SafeData

from records.templatetags.presentation import plain_title


def test_square_root_is_preserved_in_mathml_title():
    title = "Collisions at <mml:math><mml:msqrt><mml:mi>s</mml:mi></mml:msqrt></mml:math> = 13 TeV"
    assert plain_title(title) == "Collisions at sqrt(s) = 13 TeV"


def test_mathml_superscript_subscript_and_fraction_are_explicit():
    assert (
        plain_title("<math><msup><mn>10</mn><mrow><mo>-</mo><mn>17</mn></mrow></msup></math>")
        == "10^-17"
    )
    assert plain_title("<math><msub><mi>E</mi><mn>0</mn></msub></math>") == "E_0"
    assert (
        plain_title("<math><mfrac><mi>a</mi><msqrt><mi>b</mi></msqrt></mfrac></math>")
        == "(a)/(sqrt(b))"
    )
    assert plain_title("10<sup>-17</sup>") == "10^-17"


def test_tex_is_unchanged():
    title = r"Precision $10^{-17}$ at $\sqrt{s}$"
    assert plain_title(title) == title


def test_source_content_cannot_become_safe_markup():
    source = "&lt;img src=x onerror=alert(1)&gt;<script>alert(2)</script><math><msqrt><mi>s</mi></msqrt></math>"
    result = plain_title(source)
    assert not isinstance(result, SafeData)
    assert "alert(2)" not in result
    rendered = Template("{% load presentation %}{{ title|plain_title }}").render(
        Context({"title": source})
    )
    assert "<img" not in rendered
    assert "&lt;img" in rendered
    assert "sqrt(s)" in rendered


def test_article_links_use_fixed_hosts_and_encode_doi_suffix():
    from records.templatetags.presentation import doi_url, inspire_url

    assert inspire_url("2836178") == "https://inspirehep.net/literature/2836178"
    assert inspire_url("../other") == ""
    assert doi_url("javascript:alert(1)") == ""
    assert doi_url("10.1000/example#part") == "https://doi.org/10.1000/example%23part"
