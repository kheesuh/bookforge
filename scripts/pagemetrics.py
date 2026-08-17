#!/usr/bin/env python3
"""bookforge page density metrics (pagination.md §7 전처리).

판면은 tokens.json `body_frame_mm` [top,right,bottom,left]가 정본.
가구(furniture) = 60% 이상 면에 반복 출현하는 드로잉 rect/이미지 xref — 전역 제외.
면별 지표:
  reach  : 판면 내 콘텐츠 최하단 도달률 (0~1)
  ink    : 세로 점유율 — 텍스트 행은 행송(pitch) 슬롯으로 확장, 객체는 실제 bbox
  gap    : reach - ink  (공기 채움 탐지)
  lines  : 판면 내 본문 텍스트 행 수
  imgarea: 페이지 면적 대비 이미지 피복률 (전면 도판 탐지)
  pitch  : 면내 연속 행 y0 차 중앙값
"""
from collections import Counter
from statistics import median

try:  # PyMuPDF 1.24+ 신 모듈명, 구버전은 fitz만 제공
    import pymupdf as fitz
except ImportError:
    import fitz

MM2PT = 72 / 25.4


def collect_furniture(doc, ratio=0.6):
    n = doc.page_count
    draw_c, img_c = Counter(), Counter()
    for page in doc:
        seen = set()
        for d in page.get_drawings():
            r = d["rect"]
            seen.add((round(r.x0), round(r.y0), round(r.x1), round(r.y1)))
        for key in seen:
            draw_c[key] += 1
        for im in {im[0] for im in page.get_images(full=True)}:
            img_c[im] += 1
    thr = max(2, int(ratio * n))
    return ({k for k, c in draw_c.items() if c >= thr},
            {k for k, c in img_c.items() if c >= thr})


# ---- 괘선으로 둘러싸인 블록(콜아웃·표) 복원 ----
# 계선+라벨 재설계 이후 콜아웃·표의 경계는 **높이 0.3~1.2pt의 전폭 괘선**뿐이다.
# 객체 수집의 `height > 2` 필터(헤어라인·밑줄 배제 목적)에 전부 걸려, 표 108·콜아웃
# 127개짜리 책의 `_objs`가 388면 전원 0이 됐다 — G7의 float 밀림 면제가 전권에서
# 죽었다. 괘선을 **별도 키**(`_blocks`)로 복원한다: `_objs`에 넣으면 reach·ink·G8-gap이
# 함께 움직여 이미 캘리브레이션한 게이트를 흔든다.
RULE_MAX_H = 2.0    # pt — 이하를 '선'으로 본다 (실측 0.3/0.5/0.6/1.0/1.2)
RULE_MIN_W = 0.30   # 판면 폭 대비 — 실측된 블록 괘선은 전부 0.97


def _rule_blocks(rules, lines, body_size):
    """괘선 사이를 **본문 급수 행의 유무**로 갈라 블록 스팬을 만든다.

    단순히 둘씩 짝지으면 선이 3개인 블록(표: 상단·머리·하단)에서 짝이 어긋나
    이후 모든 쌍이 밀리고, 서로 다른 두 블록 사이의 본문 구간이 한 블록으로
    삼켜진다(과대평가 = 면제 남발). 대신 블록 **내부는 본문보다 작은 급수**라는
    사실을 쓴다 — 콜아웃 본문 0.95em·표 셀 9pt vs 본문 10pt. 선과 선 사이에
    본문 급수 행이 없으면 같은 블록으로 이어 붙이고, 나타나면 거기서 끊는다.
    """
    rs = sorted({(round(a, 1), round(b, 1)) for a, b in rules})   # 두 수집 경로의 중복 제거
    if len(rs) < 2:
        return []
    def region(lo, hi):
        """(본문 급수 행 존재, 지배 급수) — 두 괘선 사이 구간의 성격."""
        seg = [l for l in lines if lo < (l["y0"] + l["y1"]) / 2 < hi]
        if not seg:
            return False, None
        w = {}
        for l in seg:
            w[round(l["size"], 1)] = w.get(round(l["size"], 1), 0) + len(l["text"])
        has_body = any(abs(l["size"] - body_size) <= 0.25 for l in seg)
        return has_body, max(w, key=w.get)

    out, i = [], 0
    while i < len(rs) - 1:
        j, base = i, None
        while j + 1 < len(rs):
            has_body, dom = region(rs[j][1], rs[j + 1][0])
            if has_body or dom is None:
                # 본문이 끼면 다른 블록이고, 글이 아예 없으면 블록 내부가 아니다
                # (맞붙은 두 블록의 '하단선~상단선' 구간이 여기 해당한다)
                break
            if base is None:
                base = dom
            elif abs(dom - base) > 0.25:
                break               # 급수가 바뀌면 다른 블록(표 9pt → 콜아웃 9.5pt)
            j += 1
        if j > i:
            out.append((rs[i][0], rs[j][1]))
            i = j + 1
        else:
            i += 1                  # 짝을 못 찾은 선은 버린다(과소평가가 안전한 오차)
    return out


def _union_len(segs):
    if not segs:
        return 0.0
    segs = sorted(segs)
    total, cur0, cur1 = 0.0, segs[0][0], segs[0][1]
    for a, b in segs[1:]:
        if a > cur1:
            total += cur1 - cur0
            cur0, cur1 = a, b
        else:
            cur1 = max(cur1, b)
    return total + (cur1 - cur0)


def analyze(pdf_path, frame_mm):
    """Returns dict: {pages: [per-page dict], book_pitch, frame_pt, n_grid,
    derived_frame: (top,bottom) or None}."""
    doc = fitz.open(pdf_path)
    top, right, bottom, left = frame_mm
    fdraw, fimg = collect_furniture(doc)
    pages = []
    all_diffs = []
    for pno, page in enumerate(doc):
        pr = page.rect
        fl, ft = left * MM2PT, top * MM2PT
        fr, fb = pr.width - right * MM2PT, pr.height - bottom * MM2PT
        fh = fb - ft
        lines = []
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for ln in block.get("lines", []):
                x0, y0, x1, y1 = ln["bbox"]
                txt = "".join(s.get("text", "") for s in ln.get("spans", []))
                if not txt.strip():
                    continue
                cy = (y0 + y1) / 2
                # 판면에 x·y 모두 걸치는 행만 (세로 러닝헤드는 x로, 폴리오는 y로 배제)
                if min(x1, fr) - max(x0, fl) <= 1:
                    continue
                if not (ft - 1 <= cy <= fb + 1):
                    continue
                sizes = [s.get("size", 0) for s in ln.get("spans", []) if s.get("text", "").strip()]
                lines.append({"y0": y0, "y1": y1, "x0": x0, "x1": x1,
                              "size": round(max(sizes), 2) if sizes else 0.0,
                              "text": txt.strip()})
        lines.sort(key=lambda l: l["y0"])

        objs = []          # (y0,y1) segments inside frame, non-furniture
        img_cover = 0.0    # page-area coverage for full-bleed detection
        for im in page.get_images(full=True):
            rects = page.get_image_rects(im[0])
            for r in rects:
                # abs(Rect) = 면적 — get_area()는 PyMuPDF 1.26에서 제거돼 전 버전 호환 표기를 쓴다
                img_cover += max(0.0, abs(fitz.Rect(r)))
                if im[0] in fimg:
                    continue
                inter = fitz.Rect(r) & fitz.Rect(fl, ft, fr, fb)
                if not inter.is_empty and inter.height > 2 and inter.width > 2:
                    objs.append((inter.y0, inter.y1))
        vec_union = fitz.Rect()  # 비가구 벡터 드로잉 합집합 — SVG 도해 면적 (vecarea)
        rules = []               # 넓은 수평 괘선 = 블록 경계 마커 (아래 _rule_blocks)
        for dr in page.get_drawings():
            r = dr["rect"]
            key = (round(r.x0), round(r.y0), round(r.x1), round(r.y1))
            if key in fdraw:
                continue
            inter = fitz.Rect(r) & fitz.Rect(fl, ft, fr, fb)
            if inter.is_empty:
                continue
            if inter.height <= RULE_MAX_H and inter.width >= RULE_MIN_W * (fr - fl):
                rules.append((inter.y0, inter.y1))
                continue
            if inter.height > 2 and inter.width > 2:
                objs.append((inter.y0, inter.y1))
                vec_union |= inter
        # Typst가 임베드한 SVG 도해는 Form XObject라 get_drawings에 잡히지 않는다 —
        # bboxlog는 XObject 내부까지 내려가므로 path/shade 연산을 ink 세그먼트로 합류.
        for typ, rb in page.get_bboxlog():
            if "path" not in typ and typ != "fill-shade":
                continue
            rr = fitz.Rect(rb)
            key = (round(rr.x0), round(rr.y0), round(rr.x1), round(rr.y1))
            if key in fdraw:
                continue
            inter = rr & fitz.Rect(fl, ft, fr, fb)
            if inter.is_empty:
                continue
            if inter.height <= RULE_MAX_H and inter.width >= RULE_MIN_W * (fr - fl):
                rules.append((inter.y0, inter.y1))
                continue
            if inter.height > 2 and inter.width > 2:
                objs.append((inter.y0, inter.y1))
                vec_union |= inter
        imgarea = min(1.0, img_cover / abs(pr))
        vecarea = (min(1.0, abs(vec_union) / abs(pr))
                   if not vec_union.is_empty else 0.0)

        content_bottoms = [l["y1"] for l in lines] + [b for (_, b) in objs]
        reach = max(0.0, min(1.0, (max(content_bottoms) - ft) / fh)) if content_bottoms else 0.0
        pages.append({"page": pno + 1, "lines": len(lines),
                      "imgarea": round(imgarea, 3), "vecarea": round(vecarea, 3),
                      "reach": round(reach, 3),
                      "_lines": lines, "_objs": objs, "_rules": rules,
                      "frame": (fl, ft, fr, fb)})

    # 행송(pitch)은 "본문 급수 행"만으로 잰다 — SVG 도해 라벨·2단 블록·캡션의 촘촘한
    # 행이 중앙값을 끌어내려 n_grid를 부풀리면 G8의 lines<0.8N 판정이 전 지면 오탐된다(실측).
    size_w = Counter()
    for p in pages:
        for l in p["_lines"]:
            size_w[round(l["size"] * 2) / 2] += len(l["text"])
    body_size = size_w.most_common(1)[0][0] if size_w else 10.0
    for p in pages:
        # 괘선 블록 복원은 본문 급수가 확정된 뒤에만 가능하다
        p["_blocks"] = _rule_blocks(p.pop("_rules"), p["_lines"], body_size)
    for p in pages:
        body_lines = [l for l in p["_lines"] if abs(l["size"] - body_size) <= max(1.0, 0.1 * body_size)]
        diffs = [b["y0"] - a["y0"] for a, b in zip(body_lines, body_lines[1:])
                 if 5 < b["y0"] - a["y0"] < 40]
        all_diffs.extend(diffs)
        p["pitch"] = round(median(diffs), 2) if diffs else None

    book_pitch = round(median(all_diffs), 2) if all_diffs else None
    for p in pages:
        fl, ft, fr, fb = p["frame"]
        fh = fb - ft
        segs = list(p["_objs"])
        half = (book_pitch or 12) / 2
        for l in p["_lines"]:
            c = (l["y0"] + l["y1"]) / 2
            # pitch 슬롯과 실제 행 높이 중 큰 쪽 — 디스플레이 급수(스탯·제목) 과소평가 방지
            y0 = min(l["y0"], c - half)
            y1 = max(l["y1"], c + half)
            segs.append((max(ft, y0), min(fb, y1)))
        ink = _union_len(segs) / fh if fh > 0 else 0.0
        p["ink"] = round(min(1.0, ink), 3)
        p["gap"] = round(max(0.0, p["reach"] - p["ink"]), 3)

    # 판면 역산(드리프트 탐지): 행 10개 이상인 면들의 첫 행 y0 / reach 0.9 이상 면들의 끝 행 y1
    firsts = [p["_lines"][0]["y0"] for p in pages if p["lines"] >= 10]
    lasts = [p["_lines"][-1]["y1"] for p in pages if p["lines"] >= 10 and p["reach"] >= 0.9]
    derived = (round(median(firsts), 1) if firsts else None,
               round(median(lasts), 1) if lasts else None)

    fh = pages[0]["frame"][3] - pages[0]["frame"][1] if pages else 0
    n_grid = round(fh / book_pitch) if book_pitch else None
    doc.close()
    return {"pages": pages, "book_pitch": book_pitch, "n_grid": n_grid,
            "derived_frame": derived}


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    pdf = Path(sys.argv[1])
    frame = json.loads(sys.argv[2]) if len(sys.argv) > 2 else [20, 15, 18, 17]
    rep = analyze(pdf, frame)
    print(f"book_pitch={rep['book_pitch']} n_grid={rep['n_grid']} derived={rep['derived_frame']}")
    for p in rep["pages"]:
        print(f"p{p['page']:>3} lines={p['lines']:>3} reach={p['reach']:.3f} "
              f"ink={p['ink']:.3f} gap={p['gap']:.3f} img={p['imgarea']:.2f}")
