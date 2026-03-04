from jobfinder.streamlit_app import _prepare_description


def test_prepare_description_decodes_escaped_html_markup() -> None:
    escaped = "&lt;div class='content-intro'&gt;&lt;p&gt;Hello <strong>world</strong>&lt;/p&gt;&lt;/div&gt;"

    prepared, is_html = _prepare_description(escaped, "runwayml")

    assert is_html is True
    assert "<div" in prepared
    assert "<strong>world</strong>" in prepared


def test_prepare_description_filters_apple_boilerplate_text() -> None:
    noisy = """
    Apple
    Store
    Mac
    Apple Footer
    Privacy Policy
    Terms of Use
    Site Map
    Copyright © 2025 Apple Inc.
    """

    prepared, is_html = _prepare_description(noisy, "apple")

    assert is_html is False
    assert prepared == ""
