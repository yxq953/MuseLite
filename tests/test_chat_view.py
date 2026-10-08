from muselite_py.chat_view import render_markdown, render_messages, render_page, render_native_blocks


def test_native_reply_preserves_nested_lists_tables_and_unfinished_code():
    blocks = render_native_blocks(
        "## 总结\n\n3. 第一项\n   - **子项**\n4. 第二项\n\n> 引用\n\n"
        "| 项目 | 结果 |\n|---|---|\n| 定位 | 可用 |\n\n```python\nprint('<ok>')"
    )
    assert blocks[0]["type"] == "heading" and blocks[0]["level"] == 2
    items = [b for b in blocks if b["type"] == "list_item"]
    assert [b["marker"] for b in items] == ["3.", "•", "4."]
    assert items[1]["depth"] == 2
    assert "<strong>子项</strong>" in items[1]["html"]
    assert any(b["type"] == "quote" for b in blocks)
    table = next(b for b in blocks if b["type"] == "table")
    assert table["rows"][0][0]["header"] is True
    assert table["rows"][1][1]["html"] == "可用"
    assert blocks[-1]["text"] == "print('<ok>')"


def test_native_reply_keeps_html_and_remote_media_inert():
    blocks = render_native_blocks('<script>alert(1)</script>\n\n![远程](https://example.com/x.png)')
    assert all("<script>" not in b.get("html", "") and "<img" not in b.get("html", "") for b in blocks)
    assert "&lt;script&gt;" in blocks[0]["html"]


def test_markdown_has_headings_lists_code_and_tables():
    html = render_markdown(
        "# 标题\n\n- 一项\n\n```python\nprint('<ok>')\n```\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |"
    )
    assert "<h1>标题</h1>" in html
    assert "<li>" in html
    assert "<pre>" in html and "&lt;ok&gt;" in html
    assert "<table>" in html and "<td>2</td>" in html


def test_markdown_disables_html_scripts_links_and_remote_images():
    html = render_markdown(
        '<script>alert(1)</script>\n\n[open](javascript:alert(1)) '
        '[site](https://example.com) ![remote](https://example.com/x.png)'
    )
    assert "<script>" not in html
    assert "<a " not in html
    assert "<img " not in html
    assert "&lt;script&gt;" in html
    assert "https://example.com" in html


def test_message_roles_escape_untrusted_content_and_keep_stream_cursor():
    markup = render_messages([
        {"role": "user", "content": "<b>hi</b>"},
        {"role": "assistant", "content": "**回答**", "pending": True},
        {"role": "tool", "name": "<tool>", "content": "<value>"},
    ])
    assert "<b>hi</b>" not in markup
    assert "&lt;b&gt;hi&lt;/b&gt;" in markup
    assert "<strong>回答</strong>" in markup
    assert 'class="cursor"' in markup
    assert "&lt;tool&gt;" in markup and "&lt;value&gt;" in markup
    page = render_page([])
    assert "有什么可以帮你" in page and "museliteUpdate" in page
