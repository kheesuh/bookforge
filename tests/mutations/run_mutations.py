#!/usr/bin/env python3
"""G14 뮤테이션 스위트 — 게이트의 감도(놓치지 않는가)를 회귀 자산으로 고정한다.

PASS 상태의 책 PDF에 고의 결함을 주입한 사본을 만들고, tocgate가 각 결함을
실제로 검출하는지 어서션한다. 전부 검출되어야 exit 0.

  M1  목차 쪽번호 변조  — 첫 장의 인쇄 쪽번호를 +7 틀리게 재스탬핑 → G14-A FAIL
  M2  목차 이색(異色)   — 목차 면에 도비라 색 계열과 무관한 마젠타 라벨 주입 → G14-B FAIL
  M3  저대비 텍스트     — 본문 면에 흰 바탕 연회색(#c8c8c8) 캡션 주입 → G14-C FAIL
  M0  무변조 대조군     — 원본은 G14 전 축 PASS (오탐 없음 확인)

Usage: python3 tests/mutations/run_mutations.py <book_dir>
       (book_dir는 게이트 PASS 상태의 draft/book.pdf + outline.json 보유)
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from tocgate import _norm, find_toc_pages, g14a_toc_numbers, g14b_key_color, g14c_contrast


def load(book_dir):
    outline = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))
    titles = [c["title"].strip() for c in outline["chapters"]]
    doc = fitz.open(book_dir / "draft" / "book.pdf")
    ch_starts = sorted({p for l, _, p in doc.get_toc(simple=True) if l == 1})
    return doc, titles, ch_starts


def mutate_toc_number(doc, titles, ch_starts):
    """첫 장의 목차 인쇄 쪽번호를 지우고 +7 값으로 재스탬핑."""
    offset = ch_starts[0] - 1
    target = str(ch_starts[0] - offset)  # 첫 장 폴리오(=1)
    title_key = _norm(titles[0])
    # find_toc_pages()의 연속면 확장은 첫 목차 면을 제외할 수 있다. 그 결과 첫 반환면의
    # 절 번호 '1'을 잘못 바꿔도 실제 장 쪽번호는 살아 있어 M1이 무감각해졌다. 첫 장
    # 제목 행을 앞붙이 전체에서 직접 찾고, 같은 y 밴드의 우측 쪽번호만 변조한다.
    for pno in range(max(0, ch_starts[0] - 1)):
        page = doc[pno]
        lines = [l for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])]
        title_line = next((l for l in lines
                           if title_key in _norm("".join(s["text"] for s in l["spans"]))), None)
        if not title_line:
            continue
        band = fitz.Rect(title_line["bbox"])
        candidates = []
        for line in lines:
            for span in line["spans"]:
                r = fitz.Rect(span["bbox"])
                if span["text"].strip() == target and r.x0 > band.x1 and r.y0 < band.y1 and r.y1 > band.y0:
                    candidates.append((r.x0, r, span["size"]))
        if candidates:
            _, r, size = max(candidates)
            page.add_redact_annot(r, fill=(1, 1, 1))
            page.apply_redactions()
            page.insert_text(fitz.Point(r.x0, r.y1 - 1), str(int(target) + 7),
                             fontsize=size, color=(0, 0, 0))
            return True
    return False


def mutate_alien_color(doc, titles):
    """목차 면에 마젠타(어느 스타일과도 다른 hue) 텍스트 주입."""
    toc_pages = find_toc_pages(doc, titles)
    page = doc[toc_pages[0]]
    page.insert_text(fitz.Point(60, 60), "MUTANT", fontsize=12, color=(0.9, 0.05, 0.55))
    return True


def mutate_low_contrast(doc, ch_starts):
    """본문 면에 흰 바탕 위 #c8c8c8 8pt 텍스트 주입 (대비 1.6:1)."""
    pno = ch_starts[0]  # 첫 장 시작 다음 면쯤이 무난
    page = doc[min(pno, doc.page_count - 1)]
    page.insert_text(fitz.Point(page.rect.x1 / 2, page.rect.y1 / 2),
                     "저대비 변조 표본", fontsize=8, fontfile=str(
                         SKILL / "assets" / "fonts" / "Pretendard-Regular.ttf"),
                     fontname="F-mut", color=(0.784, 0.784, 0.784))
    return True


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    book_dir = Path(sys.argv[1]).resolve()
    results = {}

    # M0 대조군 — 원본은 전 축 PASS여야 뮤테이션 판정이 의미 있다
    doc, titles, ch_starts = load(book_dir)
    a0, _ = g14a_toc_numbers(doc, titles, ch_starts)
    b0 = g14b_key_color(doc, titles, ch_starts)
    c0, _ = g14c_contrast(doc)
    results["M0-clean"] = not a0 and not b0 and not c0
    doc.close()

    with tempfile.TemporaryDirectory() as td:
        # M1
        work = Path(td) / "m1.pdf"
        shutil.copy(book_dir / "draft" / "book.pdf", work)
        doc = fitz.open(work)
        assert mutate_toc_number(doc, titles, ch_starts), "M1 주입 실패"
        a1, _ = g14a_toc_numbers(doc, titles, ch_starts)
        results["M1-toc-number"] = bool(a1)
        doc.close()

        # M2
        work = Path(td) / "m2.pdf"
        shutil.copy(book_dir / "draft" / "book.pdf", work)
        doc = fitz.open(work)
        mutate_alien_color(doc, titles)
        b2 = g14b_key_color(doc, titles, ch_starts)
        results["M2-alien-color"] = bool(b2)
        doc.close()

        # M3
        work = Path(td) / "m3.pdf"
        shutil.copy(book_dir / "draft" / "book.pdf", work)
        doc = fitz.open(work)
        mutate_low_contrast(doc, ch_starts)
        c3, _ = g14c_contrast(doc)
        results["M3-low-contrast"] = bool(c3)
        doc.close()

    ok = all(results.values())
    for k, v in results.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    if not ok:
        sys.exit(1)
    print("전 뮤테이션 검출 — G14 감도 확인")


if __name__ == "__main__":
    main()
