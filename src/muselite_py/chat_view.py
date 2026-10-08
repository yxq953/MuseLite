"""Offline, safe HTML presentation for the chat transcript."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit

from markdown_it import MarkdownIt


def _link_open(tokens, idx, _options, env):
    href = tokens[idx].attrGet("href") or ""
    safe = href if urlsplit(href).scheme in {"http", "https"} else ""
    env.setdefault("links", []).append(safe)
    return '<span class="md-link">'


def _link_close(_tokens, _idx, _options, env):
    href = env.get("links", []).pop() if env.get("links") else ""
    suffix = f' <span class="md-url">({escape(href, quote=True)})</span>' if href else ""
    return f"</span>{suffix}"


def _image(tokens, idx, _options, _env):
    alt = tokens[idx].content or "图片"
    return f'<span class="md-image">[图片：{escape(alt)}]</span>'


_markdown = MarkdownIt("commonmark", {"html": False, "breaks": True})
_markdown.enable(["table", "strikethrough"])
_markdown.renderer.rules["link_open"] = _link_open
_markdown.renderer.rules["link_close"] = _link_close
_markdown.renderer.rules["image"] = _image


def render_markdown(source: str) -> str:
    """Render CommonMark plus tables without active HTML or remote media."""
    return _markdown.render(source or "", {})


def render_native_blocks(source: str) -> list[dict]:
    """Preserve Markdown structure for the Android native reply renderer."""
    tokens = _markdown.parse(source or "", {})
    blocks: list[dict] = []
    lists: list[dict] = []
    quote_depth = 0
    heading = 0
    table = None
    row = None
    cell = None
    for token in tokens:
        kind = token.type
        if kind in {"bullet_list_open", "ordered_list_open"}:
            lists.append({"ordered": kind == "ordered_list_open",
                          "number": int(token.attrGet("start") or 1), "pending": False})
        elif kind in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
        elif kind == "list_item_open":
            lists[-1]["pending"] = True
        elif kind == "list_item_close":
            lists[-1]["number"] += 1
        elif kind == "blockquote_open":
            quote_depth += 1
        elif kind == "blockquote_close":
            quote_depth -= 1
        elif kind == "heading_open":
            heading = int(token.tag[1:])
        elif kind == "heading_close":
            heading = 0
        elif kind == "table_open":
            table = {"type": "table", "rows": []}
        elif kind == "table_close":
            blocks.append(table)
            table = None
        elif kind == "tr_open":
            row = []
            table["rows"].append(row)
        elif kind in {"th_open", "td_open"}:
            cell = {"header": kind == "th_open", "html": ""}
            row.append(cell)
        elif kind == "inline":
            markup = _markdown.renderer.renderInline(token.children or [], _markdown.options, {})
            if table is not None:
                cell["html"] = markup
                continue
            block = {"type": "heading" if heading else "quote" if quote_depth else "paragraph",
                     "html": markup, "level": heading, "depth": len(lists)}
            if lists:
                item = lists[-1]
                block["type"] = "list_item"
                block["marker"] = (f"{item['number']}." if item["ordered"] else "•") if item["pending"] else ""
                item["pending"] = False
            blocks.append(block)
        elif kind in {"fence", "code_block"}:
            blocks.append({"type": "code", "text": token.content.rstrip("\n"),
                           "language": token.info.strip().split()[0] if token.info.strip() else "",
                           "depth": len(lists)})
        elif kind == "hr":
            blocks.append({"type": "divider"})
    return blocks


def render_messages(messages: list[dict]) -> str:
    if not messages:
        return '''<section class="welcome">
          <div class="welcome-mark">✦</div>
          <div class="welcome-eyebrow">MUSELITE · PYTHON</div>
          <h1>有什么可以帮你？</h1>
          <p>可以提问、整理思路，或让 Agent 使用工具完成任务。</p>
          <div class="welcome-hint">开始一段新对话，答案会在这里清晰呈现。</div>
        </section>'''

    cards: list[str] = []
    for message in messages:
        role = message.get("role", "assistant")
        text = str(message.get("content") or "")
        if not text and role == "assistant":
            continue
        if role == "user":
            cards.append(
                '<article class="message user"><div class="speaker">USER</div>'
                f'<div class="bubble"><div class="plain">{escape(text)}</div></div></article>'
            )
        elif role == "assistant":
            pending = '<span class="cursor"></span>' if message.get("pending") else ""
            cards.append(
                '<article class="message assistant"><div class="speaker">'
                '<span class="avatar">✦</span> MUSELITE'
                '</div><div class="bubble markdown">'
                f'{render_markdown(text)}{pending}</div></article>'
            )
        elif role == "tool":
            title = escape(str(message.get("name") or "工具结果"))
            state = "运行中" if message.get("pending") else "已完成"
            cards.append(
                '<article class="message tool"><div class="tool-head">'
                f'<span class="tool-icon">⌘</span><strong>{title}</strong><span class="tool-state">{state}</span>'
                '</div><pre>' + escape(text[:1800]) + '</pre></article>'
            )
        elif role in {"error", "status"}:
            cards.append(
                f'<aside class="notice {role}">{escape(text)}</aside>'
            )
    return "\n".join(cards)


_STYLE = r"""
:root { color-scheme: light; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: #f8faff; color: #2a374e;
       font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", sans-serif; }
#messages { max-width: 860px; margin: 0 auto; padding: 22px 15px 38px; }
.message { margin: 0 0 22px; }
.speaker { display: flex; align-items: center; gap: 7px; margin: 0 2px 7px;
           color: #7887a0; font-size: 11px; font-weight: 750; letter-spacing: .09em; }
.avatar { display: inline-flex; align-items: center; justify-content: center;
          width: 22px; height: 22px; border-radius: 8px; color: #fff; background: #789bd6;
          font-size: 13px; letter-spacing: 0; }
.bubble { overflow: hidden; padding: 14px 16px; border-radius: 18px; }
.assistant .bubble { background: #fff; border: 1px solid #e3e8f2;
                     box-shadow: 0 4px 18px rgba(15, 59, 62, .055); }
.user { display: flex; flex-direction: column; align-items: flex-end; }
.user .speaker { margin-right: 12px; }
.user .bubble { max-width: min(90%, 660px); color: #fff; background: #789bd6;
                border-bottom-right-radius: 6px; }
.plain { white-space: pre-wrap; overflow-wrap: anywhere; }
.markdown { overflow-wrap: anywhere; }
.markdown > :first-child { margin-top: 0; }
.markdown > :last-child { margin-bottom: 0; }
.markdown p { margin: 0 0 12px; }
.markdown h1, .markdown h2, .markdown h3 { line-height: 1.3; letter-spacing: -.025em;
                                            color: #354667; margin: 22px 0 10px; }
.markdown h1 { font-size: 23px; } .markdown h2 { font-size: 20px; } .markdown h3 { font-size: 17px; }
.markdown ul, .markdown ol { padding-left: 23px; margin: 8px 0 13px; }
.markdown li { padding-left: 3px; margin: 4px 0; }
.markdown li > p { margin: 0 0 5px; }
.markdown blockquote { margin: 14px 0; padding: 4px 0 4px 13px;
                       border-left: 3px solid #aabde5; color: #71809b; background: #f4f7ff; }
.markdown blockquote p { margin: 4px 9px; }
.markdown pre { overflow: auto; margin: 13px 0; padding: 13px 14px; border-radius: 12px;
                background: #38445e; color: #f4f7ff; font: 12px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; }
.markdown :not(pre) > code { padding: 2px 5px; border-radius: 5px; background: #eef3ff;
                             color: #586f9e; font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; }
.markdown table { width: 100%; display: block; overflow-x: auto; border-collapse: collapse; margin: 13px 0; }
.markdown th, .markdown td { border: 1px solid #dce3f2; padding: 7px 10px; text-align: left; }
.markdown th { background: #eef3ff; color: #4a5d80; }
.markdown tr:nth-child(even) td { background: #fbfcff; }
.markdown hr { border: 0; border-top: 1px solid #dce3f2; margin: 20px 0; }
.md-link { color: #6c8ecb; text-decoration: underline; text-underline-offset: 2px; }
.md-url, .md-image { color: #73878a; font-size: 12px; overflow-wrap: anywhere; }
.cursor { display: inline-block; width: 6px; height: 15px; margin-left: 3px;
          vertical-align: -2px; border-radius: 2px; background: #9eb6e3; animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: .15; } }
.tool { overflow: hidden; border: 1px solid #dce8e4; border-radius: 13px; background: #f0f4ff; }
.tool-head { display: flex; align-items: center; gap: 8px; padding: 9px 12px;
              color: #5b6d8e; font-size: 12px; }
.tool-icon { font-size: 15px; }
.tool-state { margin-left: auto; color: #8998b0; font-size: 11px; }
.tool pre { max-height: 160px; overflow: auto; margin: 0; padding: 0 12px 11px;
            color: #61718c; white-space: pre-wrap; word-break: break-word;
            font: 11px/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; }
.notice { margin: 9px 0 18px; padding: 10px 13px; border-radius: 10px; font-size: 13px; }
.notice.error { background: #fff0ec; color: #a23f34; border: 1px solid #f5cec5; }
.notice.status { background: #eef3ff; color: #5e7298; }
.welcome { min-height: 68vh; display: flex; flex-direction: column; align-items: center;
           justify-content: center; text-align: center; padding: 32px 12px; }
.welcome-mark { width: 66px; height: 66px; display: grid; place-items: center; border-radius: 23px;
                background: #789bd6; color: #fff; font-size: 32px;
                box-shadow: 0 10px 30px rgba(23, 101, 109, .22); }
.welcome-eyebrow { margin-top: 25px; color: #7d91b8; font-size: 11px; font-weight: 800;
                    letter-spacing: .19em; }
.welcome h1 { margin: 8px 0 2px; color: #354667; font-size: 25px; letter-spacing: -.04em; }
.welcome p { max-width: 320px; color: #647a7d; margin: 7px 0 0; }
.welcome-hint { margin-top: 26px; border: 1px solid #e1e7f2; border-radius: 99px;
                padding: 8px 13px; background: #fff; color: #7a89a5; font-size: 12px; }
"""


def render_page(messages: list[dict]) -> str:
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" '
        'content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; '
        'script-src &#39;unsafe-inline&#39;; img-src data:">'
        f"<style>{_STYLE}</style></head><body><main id=\"messages\">{render_messages(messages)}</main>"
        '<script>window.museliteUpdate=function(markup){'
        'var nearBottom=window.scrollY+window.innerHeight>=document.body.scrollHeight-180;'
        'document.getElementById("messages").innerHTML=markup;'
        'if(nearBottom){requestAnimationFrame(function(){window.scrollTo(0,document.body.scrollHeight)})}'
        'return true};window.scrollTo(0,document.body.scrollHeight);</script></body></html>'
    )
