from .html import clean_html, html_to_yaml


def test_clean_html_removes_attributes():
    html = '<div class="foo" id="bar"><p style="color:red">Hello</p></div>'
    result = clean_html(html)
    assert "class" not in result
    assert "style" not in result
    assert "Hello" in result


def test_clean_html_removes_empty_tags():
    html = "<div><span></span><p>Keep me</p></div>"
    result = clean_html(html)
    assert "Keep me" in result
    # empty span should be removed
    assert "<span>" not in result


def test_clean_html_preserves_text():
    html = "<p>Some <b>bold</b> text</p>"
    result = clean_html(html)
    assert "Some" in result
    assert "bold" in result
    assert "text" in result


def test_html_to_yaml_extracts_text():
    html = "<div><p>First</p><p>Second</p></div>"
    result = html_to_yaml(html)
    assert "First" in result
    assert "Second" in result


def test_html_to_yaml_handles_nested():
    html = "<div><ul><li>Item 1</li><li>Item 2</li></ul></div>"
    result = html_to_yaml(html)
    assert "Item 1" in result
    assert "Item 2" in result
