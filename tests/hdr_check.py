#!/usr/bin/env python3
"""러닝헤드(상단 머릿말) 대역 검사 — 단어 bbox 겹침 / 판면 이탈 / 다중행 여부.

usage: python3 hdr_check.py <pdf> <band_mm> <left_mm> <right_mm> [--footer]
  band_mm  : 검사 대역 높이(mm). 상단 0 ~ band_mm 사이의 단어를 머릿말로 본다.
  left_mm  : 판면 좌측 시작(mm)
  right_mm : 판면 우측 끝(mm)  (= trim_w - margin_right)
  --footer : 하단 대역(페이지 높이 - band_mm ~ 끝)을 검사
"""
import sys
import fitz

MM = 72 / 25.4
EPS = 0.6  # pt, 자간·커닝 오차 허용


def main():
    pdf = sys.argv[1]
    band = float(sys.argv[2]) * MM
    left = float(sys.argv[3]) * MM
    right = float(sys.argv[4]) * MM
    footer = "--footer" in sys.argv

    doc = fitz.open(pdf)
    overlaps, outs, multiline = [], [], []
    pages_with_head = 0

    for pno, page in enumerate(doc, start=1):
        H = page.rect.height
        words = page.get_text("words")
        if footer:
            band_words = [w for w in words if w[1] >= H - band]
        else:
            band_words = [w for w in words if w[3] <= band]
        if not band_words:
            continue
        pages_with_head += 1

        # 행 그룹핑 (baseline y0 반올림)
        lines = {}
        for w in band_words:
            key = round(w[1], 0)
            # 1pt 이내는 같은 행으로 병합
            hit = next((k for k in lines if abs(k - key) <= 1.5), None)
            lines.setdefault(hit if hit is not None else key, []).append(w)

        if len(lines) > 1:
            multiline.append((pno, len(lines),
                              [" ".join(x[4] for x in sorted(v, key=lambda a: a[0]))
                               for v in lines.values()]))

        for key, ws in lines.items():
            ws.sort(key=lambda a: a[0])
            for a, b in zip(ws, ws[1:]):
                if b[0] < a[2] - EPS:
                    overlaps.append((pno, a[4], b[4], round(a[2] - b[0], 2)))
            for w in ws:
                if w[0] < left - EPS or w[2] > right + EPS:
                    outs.append((pno, w[4], round(w[0] / MM, 2), round(w[2] / MM, 2)))

    print(f"pages={len(doc)}  band_pages={pages_with_head}  "
          f"band={'footer' if footer else 'header'} {band/MM:.1f}mm  "
          f"frame=[{left/MM:.1f}, {right/MM:.1f}]mm")
    print(f"OVERLAP  : {len(overlaps)}")
    for o in overlaps[:12]:
        print(f"   p{o[0]}: '{o[1]}' x '{o[2]}' 겹침 {o[3]}pt")
    print(f"OVERFLOW : {len(outs)}")
    for o in outs[:12]:
        print(f"   p{o[0]}: '{o[1]}' x=[{o[2]}, {o[3]}]mm")
    print(f"MULTILINE: {len(multiline)}")
    for m in multiline[:8]:
        print(f"   p{m[0]}: {m[1]}행 {m[2]}")
    bad = len(overlaps) + len(outs) + len(multiline)
    print("RESULT   :", "FAIL" if bad else "PASS")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
