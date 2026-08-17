#!/usr/bin/env python3
"""bookforge: deterministic Markdown(subset) -> Typst fragment converter.

Contract (chapter md):
  - first `# H1` = chapter title (opener rendered via bf-chapter; summary from outline.json)
  - `##`/`###` -> == / ===
  - paragraphs, **bold**, *em*, `code`, fenced code, > quote, lists, GFM tables, links
  - images: ![caption](path "출처: X") -> bf-fig
  - callouts (line-based, nesting depth 1):
      ::: tip 제목텍스트
      body md
      :::
    kinds: info|tip|warn|quote|stat  (stat: first line = value, second = label)
"""
from __future__ import annotations  # convert_chapter의 `str | None`을 3.9에서도 파싱

import json, re, sys, unicodedata
from pathlib import Path
from markdown_it import MarkdownIt

MD = MarkdownIt("commonmark").enable("table").enable("strikethrough")

ESC = "\\`#$&_*@<>[]~^"

def esc(text: str) -> str:
    out = []
    for ch in text:
        if ch in ESC:
            out.append("\\" + ch)
        elif ch == "/":
            out.append("\\/")  # avoid `//` comment
        else:
            out.append(ch)
    return "".join(out)

def inline(tokens) -> str:
    """Render markdown-it inline children to typst markup."""
    out = []
    for t in tokens:
        ty = t.type
        if ty == "text":
            out.append(esc(t.content))
        elif ty == "code_inline":
            content = t.content.replace("`", "\\`")
            out.append(f"#raw(\"{content_escape(t.content)}\")")
        elif ty == "strong_open":
            out.append("#strong[")
        elif ty == "strong_close":
            out.append("];")  # ';' terminates the code expr so a following '(' or '[' is not parsed as call args
        elif ty == "em_open":
            out.append("#emph[")
        elif ty == "em_close":
            out.append("];")
        elif ty == "s_open":
            out.append("#strike[")
        elif ty == "s_close":
            out.append("];")
        elif ty == "link_open":
            href = dict(t.attrs).get("href", "")
            out.append(f'#link("{content_escape(href)}")[')
        elif ty == "link_close":
            out.append("];")
        elif ty == "softbreak":
            out.append(" ")
        elif ty == "hardbreak":
            out.append(" \\\n")
        elif ty == "image":
            # inline images are promoted to block figures by block pass; ignore here
            pass
        else:
            if t.content:
                out.append(esc(t.content))
    return "".join(out)

def content_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')

def render_tokens(tokens, ctx) -> str:
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        ty = t.type
        if ty == "heading_open":
            level = int(t.tag[1])
            content = inline(tokens[i + 1].children or [])
            i += 3
            if level == 1:
                if not ctx["chapter_emitted"]:
                    summary = ctx.get("summary")
                    s = f", summary: [{esc(summary)}]" if summary else ""
                    out.append(f'#bf-chapter("{content_escape(ctx["title_raw"])}"{s})\n')
                    ctx["chapter_emitted"] = True
                # extra H1s demoted
                else:
                    out.append(f"== {content}\n")
            else:
                out.append("=" * min(level, 4) + " " + content + "\n")
            continue
        if ty == "paragraph_open":
            raw_line = (tokens[i + 1].content or "").strip()
            capm = re.match(r"^\[표\]\s*(.+?)(?:\s*\|\s*자료\s*[:：]\s*(.+))?$", raw_line)
            if capm:
                ctx["pending_tbl"] = (capm.group(1).strip(), (capm.group(2) or "").strip() or None)
                i += 3
                continue
            children = tokens[i + 1].children or []
            imgs = [c for c in children if c.type == "image"]
            if imgs and all(c.type in ("image", "softbreak", "text") and (c.type != "text" or not c.content.strip()) for c in children):
                for im in imgs:
                    attrs = dict(im.attrs)
                    src = attrs.get("src", "")
                    title = attrs.get("title", "") or ""
                    cap = inline(im.children or []) or None
                    source = None
                    m = re.match(r"출처\s*[:：]\s*(.+)", title)
                    if m:
                        source = m.group(1).strip()
                    args = [f'"{content_escape(ctx["img_prefix"] + src)}"']
                    if cap:
                        args.append(f"caption: [{cap}]")
                    if source:
                        args.append(f"source: [{esc(source)}]")
                    out.append(f'#bf-fig({", ".join(args)})\n')
            else:
                out.append(inline(children) + "\n")
            i += 3
            continue
        if ty == "fence":
            lang = (t.info or "").strip().split()[0] if (t.info or "").strip() else ""
            body = t.content.rstrip("\n")
            fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", body)), default=0) + 1)
            out.append(f"{fence}{lang}\n{body}\n{fence}\n")
            i += 1
            continue
        if ty == "blockquote_open":
            j, depth = i + 1, 1
            while j < len(tokens) and depth:
                if tokens[j].type == "blockquote_open":
                    depth += 1
                elif tokens[j].type == "blockquote_close":
                    depth -= 1
                j += 1
            inner = render_tokens(tokens[i + 1:j - 1], ctx)
            out.append(f"#quote(block: true)[{inner.strip()}]\n")
            i = j
            continue
        if ty in ("bullet_list_open", "ordered_list_open"):
            j, depth = i + 1, 1
            opener = ty
            closer = opener.replace("open", "close")
            while j < len(tokens) and depth:
                if tokens[j].type == opener:
                    depth += 1
                elif tokens[j].type == closer:
                    depth -= 1
                j += 1
            out.append(render_list(tokens[i:j], ctx))
            i = j
            continue
        if ty == "table_open":
            j = i
            while tokens[j].type != "table_close":
                j += 1
            cap = ctx.pop("pending_tbl", None)
            out.append(render_table(tokens[i:j + 1], ctx, cap=cap))
            i = j + 1
            continue
        if ty == "hr":
            out.append("#v(0.6em)#line(length: 30%, stroke: 0.5pt + luma(170))#v(0.6em)\n")
            i += 1
            continue
        i += 1
    return "\n".join(out)

# 보기 항목의 원문자는 그 자체가 마커다 — 불릿을 겹쳐 찍으면 `• ①` 이중 마커가 된다.
# 범위는 G16(qc_gate·run_swarm)의 원문자 판정과 같다.
CIRCLED_ITEM_RE = re.compile(r"^[①-⓿㉠-㉻]")


def render_list(tokens, ctx) -> str:
    ordered = tokens[0].type == "ordered_list_open"
    marker = "+" if ordered else "-"
    items, i = [], 1
    while i < len(tokens) - 1:
        if tokens[i].type == "list_item_open":
            j, depth = i + 1, 1
            while depth:
                if tokens[j].type == "list_item_open":
                    depth += 1
                elif tokens[j].type == "list_item_close":
                    depth -= 1
                j += 1
            inner = render_tokens(tokens[i + 1:j - 1], ctx).strip()
            inner = inner.replace("\n", "\n  ")
            items.append(f"{marker} {inner}")
            i = j
        else:
            i += 1
    body = "\n".join(items) + "\n"
    if not ordered and items and all(CIRCLED_ITEM_RE.match(x[2:].lstrip()) for x in items):
        # 마커를 비우되 리스트 자체는 유지한다 — 되돌이 들여쓰기(본문 시작 아래 정렬)가
        # 그대로 살아야 한다(판정 ⑥의 113/114 정렬 품질). 매달림 문단으로 바꾸면
        # 정렬 기준이 원문자 뒤로 옮겨가 그 품질이 달라진다(실측 비교).
        return "#[\n#set list(marker: []);\n" + body + "]\n"
    return body

# ---- 표 컬럼 폭: 좁은 컬럼 auto + 넓은 컬럼 비례 fr ----
# 균등 (1fr,)*n은 4자 용어 컬럼과 40자 설명 컬럼에 같은 폭을 준다. 그렇다고 전부
# 비례 fr로 주면 반대 방향으로 같은 죄를 짓는다 — 긴 컬럼이 잔여 폭을 지배해 짧은
# 컬럼이 내용 폭 이하로 압착되고 한글이 한 자씩 세로로 꺾인다(단/일/통/합).
# 그래서 자연폭이면 충분한 좁은 컬럼은 auto로 빼고, 넓은 컬럼들만 fr로 잔여 폭을
# 나눈다. fr이 하나라도 있으면 표는 여전히 판면 폭을 채운다.
TBL_AUTO_MAX = 14   # 최장 셀이 이 폭 이하(CJK 7자 상당)면 auto — 내용 자연폭이면 충분
TBL_FR_MIN = 16     # 가장 좁은 fr 컬럼의 기준 가중치(비율만 의미가 있다)
# inline()이 낸 typst 마크업 토큰 — 폭 계산 전에 걷어낸다
TYPST_RAW_RE = re.compile(r'#raw\("((?:[^"\\]|\\.)*)"\)')
TYPST_FN_OPEN_RE = re.compile(r'#(?:strong|emph|strike)\[|#link\("(?:[^"\\]|\\.)*"\)\[')


def _plain_width(s: str) -> int:
    """평문 폭 — 전각(CJK) 2, 그 외 1. NFC 정규화로 결합문자·조합 한글의 중복 계수를 막는다
    (NFD '가'는 자모 3개라 정규화 없이는 같은 글리프가 다른 폭을 갖는다)."""
    s = unicodedata.normalize("NFC", s)
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _strip_markup(s: str) -> str:
    s = TYPST_FN_OPEN_RE.sub("", s)
    s = re.sub(r"(?<!\\)\];", "", s)   # 실제 닫기만 — 이스케이프된 '\]' 뒤의 ';'는 본문
    return re.sub(r"\\(.)", r"\1", s)  # 이스케이프 역슬래시 해제


def visible_width(cell: str) -> int:
    """typst 마크업을 제거한 뒤 잰 유효 폭.

    `#raw(…)` 내용은 **코드 원문**이라 마크업 해석 대상이 아니다 — 따로 떼어 원문
    그대로 센다. 함께 벗기면 `` `C:\\tmp\\foo` ``의 역슬래시나 `` `];` ``가 마크업으로
    오인돼 사라지고, 코드·경로 컬럼이 실제보다 좁게 배정된다.
    """
    total, pos = 0, 0
    for m in TYPST_RAW_RE.finditer(cell):
        total += _plain_width(_strip_markup(cell[pos:m.start()]))
        total += _plain_width(m.group(1).replace("\\\\", "\\").replace('\\"', '"'))
        pos = m.end()
    return total + _plain_width(_strip_markup(cell[pos:]))


def column_weights(padded_rows, ncol: int):
    """컬럼별 트랙 크기 문자열 목록 — 좁으면 'auto', 넓으면 'Nfr'.

    fr 가중치는 **컬럼 내용 총량**에 비례한다. 예전엔 최장 셀 하나로 정했는데,
    용어 컬럼에 긴 항목이 하나만 있어도 상한까지 부풀고 5~8배 내용의 설명 컬럼도
    같은 상한에 눌려 **차이가 소거됐다**(실측: 내용 294 : 2691인데 폭 50:50).
    총량은 컬럼이 몇 행으로 접힐지를 결정하는 양이라 폭의 올바른 기준이다.

    다만 총량 비례만 쓰면 좁은 컬럼이 낱말도 못 담을 만큼 눌린다 — 등분 폭의 절반을
    **모든 컬럼에 더해** 비를 완만하게 만든다. `max()`로 바닥을 치면 서로 다른 두
    좁은 컬럼이 같은 값으로 뭉개져 새 역전이 생긴다(실측: 46 : 309가 둘 다 16fr).
    가산은 순서를 보존하면서 극단만 눌러 준다 — 내용 1:2는 39:61, 1:9는 23:77.
    """
    maxw = [max((visible_width(r[ci]) for r in padded_rows), default=0)
            for ci in range(ncol)]
    fr_cols = [ci for ci in range(ncol) if maxw[ci] > TBL_AUTO_MAX]
    if not fr_cols:
        return ["auto"] * ncol
    tot = {ci: max(1, sum(visible_width(r[ci]) for r in padded_rows)) for ci in fr_cols}
    floor = (sum(tot.values()) / len(tot)) / 2       # 등분 폭의 절반
    adj = {ci: t + floor for ci, t in tot.items()}   # 가산 — 순서 보존
    base = min(adj.values())
    return [f"{max(TBL_FR_MIN, round(TBL_FR_MIN * adj[ci] / base))}fr"
            if ci in adj else "auto" for ci in range(ncol)]


def render_table(tokens, ctx, cap=None) -> str:
    rows, cur = [], None
    for t in tokens:
        if t.type == "tr_open":
            cur = []
        elif t.type == "tr_close":
            rows.append(cur)
        elif t.type == "inline" and cur is not None:
            cur.append(inline(t.children or []))
    if not rows:
        return ""
    ncol = max(1, max(len(r) for r in rows))
    padded = [list(r) + [""] * (ncol - len(r)) for r in rows]
    colspec = ", ".join(column_weights(padded, ncol))
    if ncol == 1:
        colspec += ","  # 1원소 배열은 후행 쉼표가 있어야 배열로 파싱된다
    # 첫 행은 table.header로 감싼다 — 표가 면을 넘어 분할될 때 typst가 머리 행을
    # 각 조각 상단에 자동 반복한다(머리 없는 뒷조각 = 판독 불가). 머리 행 셀의
    # y는 반복본에서도 0이므로 테마의 y==0 계열 규칙(굵기·색·계선)이 그대로 산다.
    head = ", ".join(f"[{c}]" for c in padded[0])
    parts = [f"table.header({head})"]
    for r in padded[1:]:
        parts.extend(f"[{c}]" for c in r)
    tbl = f"table(columns: ({colspec}), " + ", ".join(parts) + ")"
    if cap:
        title, source = cap
        args = [f"caption: [{esc(title)}]"]
        if source:
            args.append(f"source: [{esc(source)}]")
        return f"#bf-tbl({', '.join(args)}, {tbl})\n"
    return f"#bf-tbl({tbl})\n"

# statrow는 stat보다 먼저 — 대안 순서가 뒤면 "::: statrow"가 stat(title="row")로 오탐된다
CALLOUT_RE = re.compile(r"^:::\s*(info|tip|warn|quote|statrow|stat|pull|lead|cols)\s*(.*)$")

def split_callouts(md: str):
    """Yield ('md', text) and ('callout', kind, title, body) segments."""
    lines = md.split("\n")
    buf, i = [], 0
    while i < len(lines):
        m = CALLOUT_RE.match(lines[i].strip())
        if m:
            if buf:
                yield ("md", "\n".join(buf))
                buf = []
            kind, title = m.group(1), m.group(2).strip() or None
            body, i = [], i + 1
            while i < len(lines) and lines[i].strip() != ":::":
                body.append(lines[i])
                i += 1
            i += 1
            yield ("callout", kind, title, "\n".join(body))
        else:
            buf.append(lines[i])
            i += 1
    if buf:
        yield ("md", "\n".join(buf))

def convert_chapter(md_path: Path, out_path: Path, title: str, summary: str | None,
                    img_prefix: str = "../../assets/") -> None:
    md = md_path.read_text(encoding="utf-8")
    ctx = {"chapter_emitted": False, "title_raw": title, "summary": summary, "img_prefix": img_prefix}
    parts = ['#import "../_style/theme.typ": *\n']
    for seg in split_callouts(md):
        if seg[0] == "md":
            parts.append(render_tokens(MD.parse(seg[1]), ctx))
        else:
            _, kind, title_c, body = seg
            if kind == "stat":
                ls = [l.strip() for l in body.strip().split("\n") if l.strip()]
                value = ls[0] if ls else ""
                label = ls[1] if len(ls) > 1 else ""
                parts.append(f'#bf-stat("{content_escape(value)}", "{content_escape(label)}")\n')
            elif kind == "statrow":
                # 각 행 = "값 | 라벨" — T1 하단 키 스탯 스트립 (business 팩 전용)
                cells = []
                for l in body.strip().split("\n"):
                    if not l.strip():
                        continue
                    value, _, label = l.partition("|")
                    cells.append(f'("{content_escape(value.strip())}", "{content_escape(label.strip())}")')
                parts.append(f'#bf-statrow({", ".join(cells)})\n')
            elif kind in ("lead", "cols"):
                inner = render_tokens(MD.parse(body), ctx).strip()
                parts.append(f'#bf-{kind}[{inner}]\n')
            else:
                if kind == "pull":  # 풀퀘트는 HTML 전용 — Typst 트랙에선 인용으로 강등
                    kind = "quote"
                inner = render_tokens(MD.parse(body), ctx).strip()
                targ = f"title: [{esc(title_c)}], " if title_c else ""
                parts.append(f'#bf-callout(kind: "{kind}", {targ})[{inner}]\n'.replace(", )", ")"))
    if not ctx["chapter_emitted"]:
        s = f", summary: [{esc(summary)}]" if summary else ""
        parts.insert(1, f'#bf-chapter("{content_escape(title)}"{s})\n')
    out_path.write_text("\n".join(parts), encoding="utf-8")

if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else src.stem
    summary = sys.argv[4] if len(sys.argv) > 4 else None
    convert_chapter(src, dst, title, summary)
    print(f"OK {dst}")
