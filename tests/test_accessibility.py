from pathlib import Path


STATIC = Path(__file__).parents[1] / "app" / "static"


def test_keyboard_accessible_controls_and_focus_styles():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert '<html lang="en">' in html
    assert 'for="file"' in html and 'id="file"' in html
    assert 'id="upload-form"' in html
    assert ":focus-visible" in css
    assert "aria-live" in html


def test_360px_layout_prevents_horizontal_media_overflow():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert "@media(max-width:360px)" in css
    assert ".report-table{overflow-x:auto}" in css
    assert ".cards{grid-template-columns:1fr}" in css


def test_report_rendering_escapes_text_and_uses_alt_text():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "function escapeHtml" in js
    assert 'alt="${escapeHtml' in js
    assert 'role="status"' in js
