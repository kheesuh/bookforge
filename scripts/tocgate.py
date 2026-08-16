"""G14 — 목차·디자인 정합 게이트 (qc_gate.py가 호출).

세 축:
  G14-A 인쇄 목차 쪽번호 ↔ 실제 폴리오 자기일관성.
        폴리오 관습(book-anatomy C9): 본문 1쪽부터 — 기대값 = 장 시작 절대페이지 − 오프셋
        (오프셋 = 첫 장 시작 − 1). 목차 면에서 장제목 행과 y-겹침으로 페어링한
        최우측 숫자를 인쇄값으로 읽어 대조한다. 외부 진리 불필요한 내부 일관성 검사.
  G14-B 목차 유채색 ↔ 도비라(장 오프너) 유채색의 색상(hue) 정합 — 목차가 본문과
        다른 색 계열을 쓰는 "다른 책 같은 목차"를 차단. 명도/채도 셰이드 변주는 허용.
  G14-C 유채색 텍스트의 배경 대비 WCAG 하한 — 전 면 스캔. 렌더 픽스맵에서 스팬
        주변 배경색을 추정해 대비를 계산한다. 대형(≥14pt 또는 ≥10.5pt 볼드) 3:1,
        그 외 4.5:1. 배경 추정이 불안정한 스팬(이미지·그라데이션 위)은 건너뛴다.

반환: (problems: list[str], warns: list[str], info: dict)
"""
import colorsys
import re
import unicodedata

try:
    import pymupdf as fitz
except ImportError:
    import fitz


def _norm(s):
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s​]+", "", s)


def _int_rgb(c):
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


def _is_colored(rgb, min_chroma=28):
    return max(rgb) - min(rgb) > min_chroma


def _hue(rgb):
    h, _, _ = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return h * 360


def _hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _rel_lum(rgb):
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(rgb1, rgb2):
    l1, l2 = _rel_lum(rgb1), _rel_lum(rgb2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def _spans(page):
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    yield s


def find_toc_pages(doc, titles, search_upto=7, ch_starts=None):
    """인쇄 목차 면(들). 장제목 과반이 실린 첫 면 + 히트가 이어지는 연속 면(다면 목차).

    `ch_starts`(1-idx 장 시작 면)를 주면 **앞붙이 구간으로 범위를 한정**한다. 목차는
    본문 앞에만 있으므로, 그 한정만으로 도비라(장제목 1개가 재등장하는 면)를 확실히
    배제할 수 있고 확장 가드를 "새 제목 1개 이상"으로 완화해도 안전하다.
    구 가드(2개 이상)는 목차 넘침 면이 장 하나만 싣고 넘어갈 때 — standard 분량에서
    통상적인 형태 — 그 면을 통째로 놓쳐 뒷장이 '제목 미발견'으로 구조적 FAIL이 됐다.
    """
    # 본문 첫 면(0-idx). 앞붙이 = 이 앞 구간.
    body0 = (min(ch_starts) - 1) if ch_starts else None
    limit = min(search_upto, doc.page_count) if body0 is None else min(body0, doc.page_count)
    need = max(2, (len(titles) + 1) // 2)
    hits_by_page = {}
    for pno in range(1, max(2, limit)):
        text = _norm(doc[pno].get_text())
        hits_by_page[pno] = sum(1 for t in titles if _norm(t)[:10] and _norm(t)[:10] in text)
    start = None
    for pno in sorted(hits_by_page):
        if hits_by_page[pno] >= need:
            start = pno
            break
    if start is None:  # 과반 면이 없어도, 연속 2면 합산이 과반이면 다면 목차로 인정
        for pno in sorted(hits_by_page)[:-1]:
            if hits_by_page[pno] >= 1 and hits_by_page[pno] + hits_by_page.get(pno + 1, 0) >= need:
                start = pno
                break
    if start is None:
        return []
    # 연속 면 확장은 "새 제목을 추가로 커버할 때만". 앞붙이 구간이 확정된 경우
    # (ch_starts 제공) 도비라가 애초에 범위 밖이므로 1개만 늘어도 목차 넘침으로 본다.
    # 범위를 모르면 구 가드(2개 이상)를 유지해 본문으로 번지는 것을 막는다.
    min_new = 1 if body0 is not None else 2

    def titles_on(pno):
        text = _norm(doc[pno].get_text())
        return {t for t in titles if _norm(t)[:10] and _norm(t)[:10] in text}
    out = [start]
    covered = titles_on(start)
    nxt = start + 1
    while nxt in hits_by_page and len(covered) < len(titles):
        new = titles_on(nxt) - covered
        if len(new) < min_new:
            break
        out.append(nxt)
        covered |= new
        nxt += 1
    return out


def _title_row_band(spans, t_span, title):
    """랩된 목차 제목 행의 전체 세로 범위 (y0, y1).

    긴 제목은 목차에서 2~3행으로 접힌다. 쪽번호를 **첫 줄**에 맞추는 조판(academic)도
    있고 **마지막 줄**에 맞추는 조판(essay)도 있어서, 첫 스팬의 밴드만 보면 후자에서
    쪽번호가 행 밖으로 판정돼 '행에 쪽번호 없음'이 된다. 같은 제목의 이어지는
    조각 스팬(같은 급수 + 제목의 부분문자열 + 세로로 인접)까지 밴드를 넓힌다.
    """
    ntitle = _norm(title)
    y0, y1 = t_span["bbox"][1], t_span["bbox"][3]
    size = t_span["size"]
    rest = sorted((s for s in spans if s is not t_span), key=lambda s: s["bbox"][1])
    grew = True
    while grew:
        grew = False
        for s in rest:
            frag = _norm(s["text"])
            if len(frag) < 4 or frag not in ntitle:
                continue
            if abs(s["size"] - size) > 0.6:      # 절 행·쪽번호 급수는 제외
                continue
            gap = s["bbox"][1] - y1
            if -1 <= gap <= 1.5 * size:          # 바로 다음 줄만
                y1 = max(y1, s["bbox"][3])
                y0 = min(y0, s["bbox"][1])
                grew = True
    return y0, y1


def _is_ordinal_decoration(text):
    """'01' '02' 같은 leading-zero 토큰은 장 서수 장식이지 쪽번호가 아니다."""
    t = text.strip()
    return len(t) >= 2 and t[0] == "0"


def g14a_toc_numbers(doc, titles, ch_starts):
    problems, pairs = [], []
    if not ch_starts:
        return ["장 시작 페이지 불명(북마크 부재?)"], pairs
    offset = ch_starts[0] - 1
    toc_pages = find_toc_pages(doc, titles, ch_starts=ch_starts)
    if not toc_pages:
        return ["인쇄 목차 면을 찾지 못함(장제목 과반이 실린 면 없음)"], pairs
    spans_by_page = {p: list(_spans(doc[p])) for p in toc_pages}
    for i, title in enumerate(titles):
        if i >= len(ch_starts):
            break
        expected = ch_starts[i] - offset
        key = _norm(title)[:10]
        t_span, t_page = None, None
        for p in toc_pages:
            hit = [s for s in spans_by_page[p] if key and key in _norm(s["text"])]
            if hit:
                t_span, t_page = hit[0], p
                break
        if t_span is None:
            all_joined = _norm("".join(s["text"] for p in toc_pages for s in spans_by_page[p]))
            if key not in all_joined:
                problems.append(f"목차 p{toc_pages[0] + 1}~: '{title[:16]}' 제목 미발견")
            else:
                nums = {s["text"].strip() for p in toc_pages for s in spans_by_page[p]
                        if s["text"].strip().isdigit()}
                if str(expected) not in nums:
                    problems.append(f"목차 p{toc_pages[0] + 1}~: '{title[:16]}' 기대 쪽번호 {expected} 부재")
            continue
        # 랩된 제목은 행 전체(여러 줄)를 밴드로 잡는다 — 쪽번호를 마지막 줄에 맞추는
        # 조판에서 첫 줄만 보면 놓친다.
        y0, y1 = _title_row_band(spans_by_page[t_page], t_span, title)
        # 같은 행(y 겹침)의 순수 숫자 스팬 — 좌우 무관, 서수 장식(leading zero) 제외,
        # 제목과 수평으로 가장 가까운 것이 쪽번호 (다단 목차의 이웃 칼럼 오탐 방지)
        cands = [s for s in spans_by_page[t_page]
                 if s["text"].strip().isdigit()
                 and not _is_ordinal_decoration(s["text"])
                 and not (s["bbox"][3] < y0 - 4 or s["bbox"][1] > y1 + 4)]
        if not cands:
            problems.append(f"목차 p{t_page + 1}: '{title[:16]}' 행에 쪽번호 없음")
            continue

        t_cy = (y0 + y1) / 2

        def pair_score(s):
            # 수평 거리 + 수직 중심 이탈 페널티 — 인접 행(절 목록)의 숫자가
            # 미세한 x-지터로 이기는 것을 막는다
            if s["bbox"][2] <= t_span["bbox"][0]:
                hd = t_span["bbox"][0] - s["bbox"][2]
            elif s["bbox"][0] >= t_span["bbox"][2]:
                hd = s["bbox"][0] - t_span["bbox"][2]
            else:
                hd = 0.0
            cy = (s["bbox"][1] + s["bbox"][3]) / 2
            return hd + 40 * abs(cy - t_cy)
        printed = int(min(cands, key=pair_score)["text"].strip())
        pairs.append({"title": title, "printed": printed, "expected": expected})
        if printed != expected:
            problems.append(
                f"목차 p{t_page + 1}: '{title[:16]}' 인쇄 {printed} ≠ 폴리오 {expected} "
                f"(장 시작 abs p{ch_starts[i]}, 오프셋 {offset})")
    return problems, pairs


def _accent_colors_text(page):
    return {(_int_rgb(s["color"])) for s in _spans(page) if _is_colored(_int_rgb(s["color"]))}


def _accent_colors_drawings(page):
    out = set()
    for d in page.get_drawings():
        for c in (d.get("fill"), d.get("color")):
            if c:
                rgb = tuple(int(round(v * 255)) for v in c)
                if _is_colored(rgb):
                    out.add(rgb)
    return out


def g14b_key_color(doc, titles, ch_starts, brand_hex=None, tol=36):
    problems = []
    toc_pages = find_toc_pages(doc, titles, ch_starts=ch_starts)
    if not toc_pages or not ch_starts:
        return problems  # A가 이미 잡는다
    toc_pno = toc_pages[0]
    # 다면 목차는 묶음 전체를 본다 — 넘침 면에만 이색이 있으면 놓친다
    toc_colors = set()
    for p in toc_pages:
        toc_colors |= _accent_colors_text(doc[p])
    if not toc_colors:
        return problems  # 무채색 목차 — 검사 대상 없음
    opener_hues = set()
    for p in ch_starts[:3]:  # 대표 오프너 3면
        pg = doc[p - 1]
        for rgb in _accent_colors_text(pg) | _accent_colors_drawings(pg):
            opener_hues.add(_hue(rgb))
    if brand_hex:
        try:
            b = brand_hex.lstrip("#")
            opener_hues.add(_hue(tuple(int(b[i:i + 2], 16) for i in (0, 2, 4))))
        except ValueError:
            pass
    if not opener_hues:
        return problems
    for rgb in toc_colors:
        h = _hue(rgb)
        if min(_hue_dist(h, oh) for oh in opener_hues) > tol:
            problems.append(
                f"목차 p{toc_pno + 1}: 유채색 #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                f"(hue {h:.0f}°)가 도비라·브랜드 색상 계열과 무관 (Δ>{tol}°)")
    return problems


def g14c_contrast(doc, zoom=2.0):
    """전 면 유채색 텍스트 스팬의 배경 대비. (면, 색, 대비, 하한) 위반 목록.

    반환: (problems, info) — info = {"skipped_unstable": 배경 추정 불가 스킵 수,
    "skipped_dedup": 동일 (스타일, 양자화 배경) 재검 생략 수}. 중복제거 키에는
    양자화한 배경색이 포함된다 — 같은 스타일 스팬이라도 표 얼룩무늬 행·콜아웃
    박스처럼 배경이 다르면 별건으로 재검사한다(배경 무시 dedup의 침묵 누락 방지).
    """
    problems = []
    skipped_unstable, skipped_dedup = 0, 0
    for pno in range(1, doc.page_count):  # 표지 제외(아트 배경)
        page = doc[pno]
        # 검사 대상 = 근흑(近黑) 잉크가 아닌 모든 텍스트 — 유채색 + 회색(뮤트 캡션류).
        # 근흑(#000~#333대)은 어떤 지면 배경에서도 대비가 성립하므로 제외해 비용 절감.
        colored = [s for s in _spans(page) if max(_int_rgb(s["color"])) > 96]
        if not colored:
            continue
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        w, h, nc = pix.width, pix.height, pix.n
        buf = pix.samples
        seen = set()
        for s in colored:
            rgb = _int_rgb(s["color"])
            size = s["size"]
            bold = "Bold" in s.get("font", "") or "Black" in s.get("font", "")
            floor = 3.0 if (size >= 14 or (size >= 10.5 and bold)) else 4.5
            x0, y0, x1, y1 = (int(v * zoom) for v in s["bbox"])
            # 배경 추정: bbox 바깥 2~5px 링의 최빈색
            # (dedup 키에 배경이 들어가므로 링 스캔은 dedup보다 먼저 수행해야 한다)
            ring = {}
            for (rx0, ry0, rx1, ry1) in (
                    (x0 - 5, y0 - 5, x1 + 5, y0 - 2), (x0 - 5, y1 + 2, x1 + 5, y1 + 5),
                    (x0 - 5, y0, x0 - 2, y1), (x1 + 2, y0, x1 + 5, y1)):
                for yy in range(max(0, ry0), min(h, ry1)):
                    row = yy * w * nc
                    for xx in range(max(0, rx0), min(w, rx1)):
                        o = row + xx * nc
                        px = (buf[o], buf[o + 1], buf[o + 2])
                        ring[px] = ring.get(px, 0) + 1
            if not ring:
                skipped_unstable += 1
                continue
            total = sum(ring.values())
            bg, cnt = max(ring.items(), key=lambda kv: kv[1])
            if cnt / total < 0.55:  # 배경 불균일(이미지·그라데이션) — 판정 불가
                skipped_unstable += 1
                continue
            # 중복제거 키 = 스타일 + 양자화 배경(16단계 버킷) — 같은 (색,크기,하한)
            # 스팬이라도 배경 계열이 다르면 재검사. 버킷 내 잔차는 대비에 유의미한
            # 차이를 만들지 않는다.
            key = (rgb, round(size, 1), floor, tuple(c // 16 for c in bg))
            if key in seen:
                skipped_dedup += 1
                continue
            seen.add(key)
            c = contrast(rgb, bg)
            if c < floor:
                problems.append(
                    f"p{pno + 1}: #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x} {size:.1f}pt "
                    f"'{s['text'].strip()[:14]}' 대비 {c:.2f} < {floor} "
                    f"(배경 #{bg[0]:02x}{bg[1]:02x}{bg[2]:02x})")
    return problems, {"skipped_unstable": skipped_unstable, "skipped_dedup": skipped_dedup}


def run(doc, outline, ch_starts, book, tokens):
    titles = [ch["title"].strip() for ch in outline["chapters"]]
    a_problems, pairs = g14a_toc_numbers(doc, titles, ch_starts)
    brand = book.get("brand") or tokens.get("brand_default")
    b_problems = g14b_key_color(doc, titles, ch_starts, brand)
    c_problems, c_info = g14c_contrast(doc)
    return {
        "A": {"problems": a_problems, "pairs": pairs, "ok": not a_problems},
        "B": {"problems": b_problems, "ok": not b_problems},
        "C": {"problems": c_problems, "skipped": c_info["skipped_unstable"],
              "dedup_skipped": c_info["skipped_dedup"], "ok": not c_problems},
    }
