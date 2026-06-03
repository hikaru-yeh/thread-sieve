from note_generator.infrastructure.chandra_ocr import _result_text


class Result:
    def __init__(self, *, markdown: str = "", html: str = "") -> None:
        self.markdown = markdown
        self.html = html


def test_result_text_prefers_markdown() -> None:
    assert _result_text(Result(markdown=" **diagram** ", html="<p>fallback</p>")) == "**diagram**"


def test_result_text_falls_back_to_html() -> None:
    assert _result_text(Result(html=" <p>diagram</p> ")) == "<p>diagram</p>"
