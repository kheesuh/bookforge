#!/usr/bin/env python3
"""bookforge Python 층 수정 3종 단위 검증 (표 컬럼 폭 / validate 표기 규칙 / G16)."""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / ".claude/skills/bf-produce/scripts"))

import md2typ  # noqa: E402
import qc_gate  # noqa: E402
import run_swarm  # noqa: E402

OK, FAIL = [], []


def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def cols_of(typ: str):
    """생성된 typst 조각에서 columns: (...) 안의 fr 목록을 뽑는다."""
    import re
    m = re.search(r"columns: \(([^)]*)\)", typ)
    assert m, f"columns 미발견: {typ[:120]}"
    return m.group(1)


def md_to_typ(md: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "ch.md", Path(d) / "ch.typ"
        src.write_text(md, encoding="utf-8")
        md2typ.convert_chapter(src, dst, "테스트 장", None)
        return dst.read_text(encoding="utf-8")


# ============================================================ A. 표 컬럼 폭
print("\n=== A. md2typ 표 트랙 (좁은 컬럼 auto + 넓은 컬럼 비례 fr) ===")

# A1 visible_width 원자 검사
check("A1a CJK 2 / ASCII 1", md2typ.visible_width("가나다") == 6 and md2typ.visible_width("abc") == 3,
      f'"가나다"={md2typ.visible_width("가나다")}, "abc"={md2typ.visible_width("abc")}')
check("A1b #strong[] 마크업 제거", md2typ.visible_width("#strong[용어];") == md2typ.visible_width("용어"),
      f'strong={md2typ.visible_width("#strong[용어];")} plain={md2typ.visible_width("용어")}')
_a1c = md2typ.visible_width('#raw("abcd")')
check("A1c #raw() 내용만 계산", _a1c == 4, f"={_a1c}")
_a1d = md2typ.visible_width("\\#\\_x")
check("A1d 이스케이프 역슬래시 제거", _a1d == 3, f"={_a1d}")
_a1e = md2typ.visible_width("\\];")
check("A1e 이스케이프된 ']' 보존", _a1e == 2, f"={_a1e}")
check("A1f 빈 셀 0", md2typ.visible_width("") == 0)
check("A1g #link 프리픽스 제거",
      md2typ.visible_width('#link("https://very.long.example.com/x")[문서];') == md2typ.visible_width("문서"))

# --- 표 트랙 산출: 좁은 컬럼 auto + 넓은 컬럼 비례 fr ---
def tracks(md):
    """생성된 typst의 columns 트랙 목록(문자열)."""
    return [x.strip() for x in cols_of(md_to_typ(md)).split(",") if x.strip()]


def raw_widths(md):
    """진단용 — 각 컬럼의 클램프 전 유효 폭."""
    import markdown_it
    toks = md2typ.MD.parse(md)
    i = next(k for k, t in enumerate(toks) if t.type == "table_open")
    j = next(k for k, t in enumerate(toks) if t.type == "table_close")
    rows, cur = [], None
    for t in toks[i:j + 1]:
        if t.type == "tr_open":
            cur = []
        elif t.type == "tr_close":
            rows.append(cur)
        elif t.type == "inline" and cur is not None:
            cur.append(md2typ.inline(t.children or []))
    n = max(len(r) for r in rows)
    pad = [list(r) + [""] * (n - len(r)) for r in rows]
    return [max(md2typ.visible_width(r[c]) for r in pad) for c in range(n)]


# A2 혼합 — 좁은 컬럼 2 + 넓은 컬럼 2 (팀리드 렌더 검증에서 나온 압착 케이스)
MIXED4 = """# 테스트 장

| 전략 | 분기 수명 | 설명 | 적용 조건 |
| --- | --- | --- | --- |
| 단일 통합 | 2주 이내 | 모든 변경을 하나의 줄기에 모아 지속적으로 통합하는 방식으로 충돌을 조기에 드러낸다 | 팀 규모가 작고 배포 주기가 짧을 때 |
| 기능 분기 | 1개월 | 기능 단위로 줄기를 떼어 독립 개발한 뒤 검수 후 병합하는 방식 | 검수 게이트가 필요한 조직 |
"""
tk, rw = tracks(MIXED4), raw_widths(MIXED4)
check("A2 혼합 4컬럼 — 좁은 2개는 auto", tk[0] == "auto" and tk[1] == "auto",
      f"tracks={tk} raw={rw}")
check("A2b 넓은 2개는 fr", tk[2].endswith("fr") and tk[3].endswith("fr"), f"tracks={tk} raw={rw}")
check("A2c 넓은 컬럼끼리는 내용 비례 유지",
      int(tk[2][:-2]) >= int(tk[3][:-2]), f"tracks={tk} raw={rw}")
# 폭은 이제 절대 상한이 아니라 **내용 총량 비**로 정해진다(B-9 수리)
check("A2d 내용이 많은 컬럼이 더 넓다", int(tk[2][:-2]) >= int(tk[3][:-2]), f"tracks={tk} raw={rw}")

# A3 전부 좁음 → 전부 auto (표가 자연폭 — 용어표에 정당)
NARROW = """# 테스트 장

| 항목 | 값 | 비고 |
| --- | --- | --- |
| 가나다 | 라마바 | 사아자 |
"""
tk = tracks(NARROW)
check("A3 전부 좁은 표 → 전 컬럼 auto", tk == ["auto", "auto", "auto"], f"tracks={tk}")

# A4 전부 넓음 → 전부 fr (판면 폭 100% 유지)
WIDE = """# 테스트 장

| 첫째 개념의 정의와 배경 설명 | 둘째 개념의 정의와 배경 설명 |
| --- | --- |
| 여러 워커가 장을 나눠 동시에 집필하는 병렬 생성 구조를 가리킨다 | 조판 결함을 기계적으로 검출해 최종본 승격을 막는 검사 관문이다 |
"""
tk = tracks(WIDE)
check("A4 전부 넓은 표 → 전 컬럼 fr", all(t.endswith("fr") for t in tk) and len(tk) == 2,
      f"tracks={tk}")

# A5 auto/fr 문턱 경계 — 유효 폭 14는 auto, 15는 fr(하한 16으로 클램프)
BOUND = """# 테스트 장

| A | B |
| --- | --- |
| 가나다라마바사 | 가나다라마바사x |
"""
tk, rw = tracks(BOUND), raw_widths(BOUND)
check("A5 유효 폭 14 → auto / 15 → fr", rw == [14, 15] and tk == ["auto", "16fr"],
      f"tracks={tk} raw={rw}")

# A6 1컬럼 — 좁으면 auto, 넓으면 fr. 둘 다 후행 쉼표(1원소 배열)
ONE_N = """# 테스트 장

| 항목 |
| --- |
| 가 |
"""
ONE_W = """# 테스트 장

| 항목 |
| --- |
| 여러 워커가 장을 나눠 동시에 집필하는 병렬 생성 구조를 가리킨다 |
"""
c_n, c_w = cols_of(md_to_typ(ONE_N)), cols_of(md_to_typ(ONE_W))
check("A6 1컬럼 좁음 → (auto,)", c_n.strip() == "auto,", f"columns=({c_n})")
check("A6b 1컬럼 넓음 → 단일 fr + 후행 쉼표",
      c_w.strip().endswith("fr,") and c_w.count(",") == 1, f"columns=({c_w})")

# A7 빈 셀 표 — 죽지 않고 auto
EMPTY = """# 테스트 장

| | |
| --- | --- |
| | |
"""
try:
    check("A7 빈 셀 표 — 예외 없음 + auto", tracks(EMPTY) == ["auto", "auto"], f"{tracks(EMPTY)}")
except Exception as e:  # noqa: BLE001
    check("A7 빈 셀 표 — 예외 없음", False, repr(e))

# A8 마크업이 폭을 부풀리지 않는다 (넓은 대역에서 확인 — 볼드 셀 vs 평문 셀 동일 fr)
BOLD = """# 테스트 장

| 헤더 | 헤더 |
| --- | --- |
| **여러 워커가 장을 나눠 동시에 집필하는 구조** | 여러 워커가 장을 나눠 동시에 집필하는 구조 |
"""
tk = tracks(BOLD)
check("A8 볼드 셀과 평문 셀 동일 트랙", tk[0] == tk[1] and tk[0].endswith("fr"), f"tracks={tk}")

# A9 정수 fr만 (12.0fr 금지)
check("A9 정수 fr 출력", ".0fr" not in cols_of(md_to_typ(MIXED4)), cols_of(md_to_typ(MIXED4)))

# A10 행 길이 불일치·3컬럼 정상 산출
RAGGED = """# 테스트 장

| A | B | C |
| --- | --- | --- |
| 하나 | 둘 | 셋 |
"""
try:
    check("A10 3컬럼 정상 산출", len(tracks(RAGGED)) == 3, f"{tracks(RAGGED)}")
except Exception as e:  # noqa: BLE001
    check("A10 3컬럼 정상 산출", False, repr(e))


# ============================================ B. run_swarm.validate() 표기 규칙
print("\n=== B. run_swarm validate() 신규 하드 위반 ===")


def notation(body: str):
    """장 본문(H1 포함)을 validate에 태워 (위반, 경고)를 돌려준다."""
    v, w, _ = run_swarm.validate("# 테스트 장\n\n" + body, "테스트 장")
    return v, w


def has(items, kw):
    return any(kw in i for i in items)


# B1 정상 산문
v, w = notation("보통의 문장이다. 특별한 표기 위반이 없다.\n")
check("B1 정상 산문 위반 0", not v and not w, f"v={v} w={w}")

# B2~B4 엠대시 경계 (0 / 3 / 4)
v, w = notation("문장 하나 — 둘 — 셋 — 이렇게 셋.\n")
check("B2 엠대시 정확히 3개 → WARN(위반 아님)",
      not has(v, "엠대시") and has(w, "엠대시 3개"), f"v={v} w={w}")
v, w = notation("하나 — 둘 — 셋 — 넷 — 이렇게 넷.\n")
check("B3 엠대시 4개 → 하드 위반", has(v, "엠대시 남용(4개)") and not has(w, "엠대시"), f"v={v} w={w}")
v, w = notation("엠대시가 하나도 없는 문장이다.\n")
check("B4 엠대시 0개 → 무반응", not has(v, "엠대시") and not has(w, "엠대시"), f"v={v} w={w}")
v, w = notation("하나 — 이렇게 하나.\n")
check("B4b 엠대시 1개 → WARN", has(w, "엠대시 1개") and not has(v, "엠대시"), f"w={w}")

# B5 원문자 경계 (2 / 3)
v, w = notation("보기는 ① 첫째 ② 둘째 이다.\n")
check("B5 원문자 2개 → 통과", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("보기는 ① 첫째 ② 둘째 ③ 셋째 이다.\n")
check("B6 원문자 3개 → 하드 위반", has(v, "보기·선택지"), f"v={v}")
v, w = notation("보기:\n\n- ① 첫째\n- ② 둘째\n- ③ 셋째\n")
check("B7 원문자가 줄마다 1개(리스트) → 통과", not has(v, "보기·선택지"), f"v={v}")

# B8 1) 2) 3) 경계
v, w = notation("근거는 1) 비용 2) 속도 이다.\n")
check("B8 '1) 2)' 2개 → 통과", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("근거는 1) 비용 2) 속도 3) 신뢰 이다.\n")
check("B9 '1) 2) 3)' 3개 → 하드 위반", has(v, "보기·선택지"), f"v={v}")
v, w = notation("괄호형 (1) 비용 (2) 속도 (3) 신뢰 는 규칙 밖이다.\n")
check("B10 '(1)(2)(3)' 괄호형은 비대상", not has(v, "보기·선택지"), f"v={v}")

# B11 코드블록 안 엠대시·원문자는 무시
v, w = notation("본문이다.\n\n```text\n하나 — 둘 — 셋 — 넷 — 다섯 —\n① ② ③ ④\n```\n\n끝.\n")
check("B11 코드블록 안 엠대시 4개+ 무시", not has(v, "엠대시") and not has(v, "보기·선택지"),
      f"v={v} w={w}")

# B12 인라인 코드 안 엠대시 무시
v, w = notation("설명 `a — b — c — d — e` 를 쓴다.\n")
check("B12 인라인 코드 안 엠대시 무시", not has(v, "엠대시") and not has(w, "엠대시"), f"v={v} w={w}")

# B13 표 행의 원문자는 오탐 제외
v, w = notation("| A | B | C |\n| --- | --- | --- |\n| ① | ② | ③ |\n")
check("B13 표 행 ①②③ 오탐 제외", not has(v, "보기·선택지"), f"v={v}")

# B14 기존 위반 규칙 회귀 (H1 불일치 / HTML / 이미지 경로 / #### )
v, _, _ = run_swarm.validate("# 다른 제목\n\n본문\n", "테스트 장")
check("B14a H1 불일치 회귀", has(v, "첫 줄이"), f"v={v}")
v, _ = notation("<div>x</div>\n")
check("B14b HTML 태그 회귀", has(v, "HTML 태그"), f"v={v}")
v, _ = notation("![캡션](../img/a.svg)\n")
check("B14c 이미지 경로 회귀", has(v, "이미지 경로 위반"), f"v={v}")
v, _ = notation("#### 너무 깊은 제목\n")
check("B14d #### 회귀", has(v, "####"), f"v={v}")


# B15~B18 softbreak 접힘 — 한 문단 안 생줄 나열 (사용자가 실제로 본 결함)
v, w = notation("확인 문제: 다음 중 옳은 것은?\n① 보기 하나\n② 보기 둘\n③ 보기 셋\n")
check("B15 문단 안 생줄 ①②③ → 하드 위반", has(v, "보기·선택지"), f"v={v}")
v, w = notation("확인 문제:\n\n1. 다음 중 옳은 것은?\n   - ① 보기 하나\n   - ② 보기 둘\n   - ③ 보기 셋\n")
check("B16 규정 문법(번호 문제 + 들여쓴 보기 리스트) → 통과", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("첫 문단 ① 가.\n\n둘째 문단 ② 나.\n\n셋째 문단 ③ 다.\n")
check("B17 문단이 다르면 합산 안 함 → 통과", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("- ① 가 ② 나 ③ 다\n- 다른 항목\n")
check("B18 리스트 항목 한 줄에 보기 3개 → 하드 위반", has(v, "보기·선택지"), f"v={v}")
v, w = notation("근거:\n1) 비용\n2) 속도\n3) 신뢰\n")
check("B19 '1)' 리스트 항목 줄나눔 → 통과", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("근거는 이렇다.\n비용 1)\n속도 2)\n신뢰 3)\n")
check("B20 생줄 'N)' 문단 합산 3개 → 하드 위반", has(v, "보기·선택지"), f"v={v}")


# ================================================== C. qc_gate G16 + 규칙 동치
print("\n=== C. qc_gate G16 (검사 로직 + run_swarm 동치) ===")

FIXTURES = {
    "정상": "# 장\n\n평범한 문장이다. 위반이 없다.\n",
    "엠대시3": "# 장\n\n하나 — 둘 — 셋 — 끝.\n",
    "엠대시4": "# 장\n\n하나 — 둘 — 셋 — 넷 — 끝.\n",
    "원문자2": "# 장\n\n보기는 ① 가 ② 나 이다.\n",
    "원문자3": "# 장\n\n보기는 ① 가 ② 나 ③ 다 이다.\n",
    "번호3": "# 장\n\n근거는 1) 가 2) 나 3) 다 이다.\n",
    "코드블록내": "# 장\n\n```\n— — — — ① ② ③\n```\n\n본문.\n",
    "인라인코드내": "# 장\n\n`— — — —` 이다.\n",
    "표행": "# 장\n\n| A | B | C |\n| --- | --- | --- |\n| ① | ② | ③ |\n",
    "복합위반": "# 장\n\n보기 ① 가 ② 나 ③ 다.\n\n하나 — 둘 — 셋 — 넷 — 끝.\n",
    "문단접힘": "# 장\n\n확인 문제?\n① 가\n② 나\n③ 다\n",
    "규정문법": "# 장\n\n1. 확인 문제?\n   - ① 가\n   - ② 나\n   - ③ 다\n",
    # --- codex 적대 리뷰 결함 3~6의 재현 입력 (양쪽 구현 동치까지 검사) ---
    "괄호참조": "# 장\n\n(주 3) 참고, (표 4) 참고, (그림 5) 참고.\n",
    "한글원문자": "# 장\n\n보기 \u326e 첫째 \u326f 둘째 \u3270 셋째.\n",
    "영문원문자": "# 장\n\n보기 \u24d0 first \u24d1 second \u24d2 third.\n",
    "파이프없는표": "# 장\n\n항목 | 상태 | 결과\n---|---|---\n\u2460 준비 | \u2461 실행 | \u2462 검증\n",
    "선행파이프산문": "# 장\n\n| 선택지는 \u2460 첫째 \u2461 둘째 \u2462 셋째이다.\n",
    "틸드펜스": "# 장\n\n~~~text\n\u2460 \u2461 \u2462\n\u2014 \u2014 \u2014 \u2014\n~~~\n\n본문.\n",
    "백틱4펜스": "# 장\n\n````text\n\u2460 \u2461 \u2462\n\u2014 \u2014 \u2014 \u2014\n````\n\n본문.\n",
    "들여쓴펜스": "# 장\n\n  ```text\n  \u2460 \u2461 \u2462\n  \u2014 \u2014 \u2014 \u2014\n  ```\n\n본문.\n",
}
EXPECT_HARD = {"엠대시4", "원문자3", "번호3", "복합위반", "문단접힘",
               "한글원문자", "영문원문자", "선행파이프산문"}
EXPECT_WARN = {"엠대시3"}

with tempfile.TemporaryDirectory() as d:
    bd = Path(d)
    (bd / "chapters").mkdir()
    chapters = []
    for i, (name, body) in enumerate(sorted(FIXTURES.items()), 1):
        f = f"ch-{i:02d}.md"
        (bd / "chapters" / f).write_text(body, encoding="utf-8")
        chapters.append({"file": f, "title": "장", "_name": name})
    outline = {"chapters": chapters}
    for ch in chapters:
        one = {"chapters": [ch]}
        probs, warns = qc_gate.g16_notation_check(bd, one)
        name = ch["_name"]
        want_hard = name in EXPECT_HARD
        want_warn = name in EXPECT_WARN
        check(f"C-G16 {name}: HARD={want_hard} WARN={want_warn}",
              bool(probs) == want_hard and bool(warns) == want_warn,
              f"problems={probs} warns={warns}")

        # 동치: run_swarm.validate()의 판정과 일치해야 한다 (교착 방지)
        rs_prose = run_swarm.strip_code((bd / "chapters" / ch["file"]).read_text(encoding="utf-8"))
        rs_v, rs_w = run_swarm.notation_problems(rs_prose)
        check(f"C-동치 {name}", bool(rs_v) == bool(probs) and bool(rs_w) == bool(warns),
              f"run_swarm=({rs_v},{rs_w}) qc_gate=({probs},{warns})")

    # 복합 위반은 2건 (보기 + 엠대시)
    comp = [c for c in chapters if c["_name"] == "복합위반"][0]
    probs, _ = qc_gate.g16_notation_check(bd, {"chapters": [comp]})
    check("C-복합 위반 2건", len(probs) == 2, f"{probs}")

    # 산문 추출 정규식 동치 (strip_code vs _g16_prose)
    for name, body in FIXTURES.items():
        check(f"C-strip 동치 {name}",
              run_swarm.strip_code(body) == qc_gate._g16_prose(body))

    # 없는 장 파일은 건너뛴다
    probs, warns = qc_gate.g16_notation_check(bd, {"chapters": [{"file": "nope.md", "title": "x"}]})
    check("C-부재 장 무시", probs == [] and warns == [])


# ====================== D. codex 적대 리뷰 결함 7건 재현 (2026-08-16)
print("\n=== D. 적대 리뷰 결함 7건 재현 회귀 ===")

# D1 (결함 1, 오탐) #raw 내용을 마크업으로 재해석해 폭 축소
_d1a = md2typ.visible_width('#raw("C:\\\\tmp\\\\foo")')       # 표시 문자열 C:\tmp\foo = 10자
_d1b = md2typ.visible_width('#raw("];")')                      # 표시 문자열 ]; = 2자
_d1c = md2typ.visible_width('#raw("#strong[abcdefghijklmnopqrst];")')  # 30자
check("D1a #raw 경로의 역슬래시 보존", _d1a == 10, f"={_d1a} (기대 10)")
check("D1b #raw 안의 '];' 보존", _d1b == 2, f"={_d1b} (기대 2)")
check("D1c #raw 안의 마크업 문자열 보존", _d1c == 30, f"={_d1c} (기대 30)")
_d1d = md2typ.visible_width('앞 #raw("];") 뒤 #strong[가];')
check("D1d raw 밖 마크업은 여전히 제거", _d1d == md2typ.visible_width("앞 ") + 2
      + md2typ.visible_width(" 뒤 ") + 2, f"={_d1d}")

# D2 (결함 2, 오탐) 유니코드 정규화 형태에 따른 폭 불일치
_nfc, _nfd = "\uac00", "\u1100\u1161"          # '가' NFC / NFD
_e1, _e2 = "\u00e9", "e\u0301"                  # 'é' NFC / NFD
check("D2a NFD 한글도 NFC와 같은 폭", md2typ.visible_width(_nfd) == md2typ.visible_width(_nfc) == 2,
      f"NFD={md2typ.visible_width(_nfd)} NFC={md2typ.visible_width(_nfc)}")
check("D2b NFD 라틴 결합문자도 1폭", md2typ.visible_width(_e2) == md2typ.visible_width(_e1) == 1,
      f"NFD={md2typ.visible_width(_e2)} NFC={md2typ.visible_width(_e1)}")

# D3 (결함 3, 오탐) 괄호 참조 표기가 'N)' 나열로 오탐
v, w = notation("(주 3) 참고, (표 4) 참고, (그림 5) 참고.\n")
check("D3a '(주 3) (표 4) (그림 5)' 오탐 아님", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("각주 (1) 과 (2) 와 (3) 을 본다.\n")
check("D3b '(1)(2)(3)' 여전히 비대상", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("근거는 1) 비용 2) 속도 3) 신뢰 이다.\n")
check("D3c 괄호 밖 'N)' 3개는 여전히 위반", has(v, "보기·선택지"), f"v={v}")

# D4 (결함 4, 미탐) ①-⑳ 밖 원문자 계열
v, w = notation("보기 ㉮ 첫째 ㉯ 둘째 ㉰ 셋째.\n")
check("D4a 한글 원문자 ㉮㉯㉰ 검출", has(v, "보기·선택지"), f"v={v}")
v, w = notation("보기 \u24d0 first \u24d1 second \u24d2 third.\n")
check("D4b 영문 원문자 ⓐⓑⓒ 검출", has(v, "보기·선택지"), f"v={v}")
v, w = notation("보기 \u2474 하나 \u2475 둘 \u2476 셋.\n")
check("D4c 괄호 숫자 ⑴⑵⑶ 검출", has(v, "보기·선택지"), f"v={v}")
v, w = notation("보기 ㉮ 첫째 ㉯ 둘째.\n")
check("D4d 확대 계열도 2개는 통과", not has(v, "보기·선택지"), f"v={v}")

# D5 (결함 5) GFM 표 판정
v, w = notation("항목 | 상태 | 결과\n---|---|---\n\u2460 준비 | \u2461 실행 | \u2462 검증\n")
check("D5a 선행 '|' 없는 유효 표 오탐 아님", not has(v, "보기·선택지"), f"v={v}")
v, w = notation("| 선택지는 \u2460 첫째 \u2461 둘째 \u2462 셋째이다.\n")
check("D5b 선행 '|' 하나뿐인 산문은 검사됨", has(v, "보기·선택지"), f"v={v}")
v, w = notation("본문 \u2460 가 \u2461 나 \u2462 다.\n항목 | 값\n---|---\na | b\n")
check("D5c 같은 블록의 표 앞 산문 위반은 잡힌다", has(v, "보기·선택지"), f"v={v}")
v, w = notation("| A | B | C |\n| --- | --- | --- |\n| \u2460 | \u2461 | \u2462 |\n")
check("D5d 표준 파이프 표는 여전히 제외", not has(v, "보기·선택지"), f"v={v}")

# D6 (결함 6, 미탐) 지원 펜스 확장
v, w = notation("본문.\n\n~~~text\n\u2460 \u2461 \u2462\n\u2014 \u2014 \u2014 \u2014\n~~~\n\n끝.\n")
check("D6a ~~~ 펜스 내용 무시", not has(v, "보기·선택지") and not has(v, "엠대시"), f"v={v} w={w}")
v, w = notation("본문.\n\n````text\n\u2460 \u2461 \u2462\n\u2014 \u2014 \u2014 \u2014\n````\n\n끝.\n")
check("D6b 백틱 4개 펜스 내용 무시", not has(v, "보기·선택지") and not has(v, "엠대시"), f"v={v} w={w}")
v, w = notation("본문.\n\n  ```text\n  \u2460 \u2461 \u2462\n  \u2014 \u2014 \u2014 \u2014\n  ```\n\n끝.\n")
check("D6c 2칸 들여쓴 펜스 내용 무시", not has(v, "보기·선택지") and not has(v, "엠대시"), f"v={v} w={w}")
v, w = notation("본문.\n\n```text\n~~~ 는 닫지 못한다 \u2014 \u2014 \u2014 \u2014\n```\n\n끝.\n")
check("D6d 다른 종류 펜스로는 안 닫힌다", not has(v, "엠대시"), f"v={v} w={w}")
v, w = notation("본문.\n\n```text\n\u2460 \u2461 \u2462\n```\n\n보기 \u2460 가 \u2461 나 \u2462 다.\n")
check("D6e 펜스 밖 위반은 그대로 검출", has(v, "보기·선택지"), f"v={v}")

# D7 (결함 7) outline 장 파일 중복 가드
import subprocess as _sp
RUNNER = REPO / ".claude/skills/bf-produce/scripts/run_swarm.py"
with tempfile.TemporaryDirectory() as d:
    bd = Path(d); (bd / "chapters").mkdir()
    def _run(chs):
        (bd / "outline.json").write_text(json.dumps({"chapters": chs}, ensure_ascii=False),
                                         encoding="utf-8")
        return _sp.run([sys.executable, str(RUNNER), str(bd), "--skill", str(REPO), "--dry-run"],
                       capture_output=True, text=True)
    r = _run([{"file": "ch-01.md", "title": "첫 장"}, {"file": "ch-01.md", "title": "다른 장"}])
    check("D7a 동일 file 중복 → 즉시 종료", r.returncode != 0 and "중복" in (r.stdout + r.stderr),
          f"rc={r.returncode} {(r.stderr or r.stdout).strip()[:90]}")
    r = _run([{"file": "part-a/ch-01.md", "title": "A"}, {"file": "part-b/ch-01.md", "title": "B"}])
    check("D7b 동일 stem(다른 경로) 중복 → 즉시 종료",
          r.returncode != 0 and "stem" in (r.stdout + r.stderr),
          f"rc={r.returncode} {(r.stderr or r.stdout).strip()[:90]}")
    r = _run([{"file": "ch-01.md", "title": "첫 장"}, {"file": "ch-02.md", "title": "둘째 장"}])
    check("D7c 고유 파일명은 정상 진행", r.returncode == 0 and "dry-run" in r.stdout,
          f"rc={r.returncode} {r.stdout.strip()[:70]}")



# ============ E. G8-STRETCH 표제 여백 캘리브레이션 (2026-08-16)
# 게이트를 느슨하게 여는 방향의 변경이므로, 표제가 없는 면의 임계가 종전(0.18)
# 그대로임을 먼저 못박는다 — 진짜 공기 채움(행간 확대·빈 줄)은 표제 가산을 못 받는다.
print("\n=== E. G8-STRETCH 캘리브레이션 ===")

def thr(style, sizes, body=10.0):
    return qc_gate.g8_gap_threshold(style, [{"size": z} for z in sizes], body)

# E1 안전 속성 — 표제 0개 면은 임계 0.18 불변
t, h = thr("academic", [10.0] * 25)
check("E1 표제 없는 면 임계 0.18 불변 (진짜 공기 채움 계속 잡음)", t == 0.18 and h == 0,
      f"thr={t} heads={h}")
for g in (0.19, 0.30, 0.45, 0.90):
    t, _ = thr("academic", [10.0] * 25)
    check(f"E1b 표제 0개·gap {g} → 적발", g > t, f"thr={t}")

# E2 표제 판별 대역 — academic H2 11.5(1.15)·practical H2 11.3(1.13)은 잡고
#    academic H3 10.5(1.05)는 제외 (본문 10.0 기준)
_, h = thr("academic", [10.0, 11.5, 10.0])
check("E2a academic H2 11.5pt 포착", h == 1, f"heads={h}")
_, h = thr("practical", [10.0, 11.3, 10.0])
check("E2b practical H2 11.3pt 포착", h == 1, f"heads={h}")
_, h = thr("academic", [10.0, 10.5, 10.0])
check("E2c academic H3 10.5pt 제외", h == 0, f"heads={h}")
_, h = thr("academic", [10.0, 11.19, 11.21])
check("E2d 문턱 1.12 경계(11.19 제외 / 11.21 포착)", h == 1, f"heads={h}")

# E3 가산·상한
t, _ = thr("academic", [10.0, 11.5])
check("E3a 표제 1개 → 0.25", abs(t - 0.25) < 1e-9, f"thr={t}")
t, _ = thr("academic", [10.0, 11.5, 11.5, 11.5])
check("E3b 표제 3개 → 0.39", abs(t - 0.39) < 1e-9, f"thr={t}")
t, _ = thr("business", [10.0] + [16.0] * 9)
check("E3c 표제 9개 → 상한 0.45", t == 0.45, f"thr={t}")
t, _ = thr("essay", [10.0, 12.0, 12.0])
check("E3d 전 스타일 가산 적용(essay 2개 → 0.32)", abs(t - 0.32) < 1e-9, f"thr={t}")

# E4 insight는 기왕의 식 유지(실측 픽스처 부재 — 상한도 없음)
t, _ = thr("insight", [10.0, 14.0, 14.0, 14.0])
check("E4 insight 식 유지 0.28+0.10*(heads-1)", abs(t - 0.48) < 1e-9, f"thr={t}")

# E5 실측 회귀 — 픽스처 실제 면의 (gap, 표제 크기)로 판정 재현
#    출처: /tmp/bf-typo-fix/<style>/draft/book.pdf 실측 (수리 전 academic p10/p13·essay p15 FAIL)
REAL = [  # (style, page, gap, 면의 행 크기 목록 요약, body, 기대: 적발 여부)
    ("academic", 6,  0.179, [10.0]*19 + [11.5, 11.5, 10.5, 10.5], 10.0, False),
    ("academic", 10, 0.182, [10.0]*17 + [11.5, 11.5, 11.5, 10.5, 10.5], 10.0, False),
    ("academic", 13, 0.191, [10.0]*16 + [11.5, 11.5, 11.5, 10.5, 10.5], 10.0, False),
    ("academic", 16, 0.087, [10.0]*14 + [10.5], 10.0, False),
    ("essay",    15, 0.272, [10.0]*13 + [12.0, 12.0], 10.0, False),
    ("essay",    11, 0.090, [10.0]*11, 10.0, False),
    ("business", 4,  0.245, [10.5]*23 + [16.0]*3 + [12.0]*5, 10.5, False),
    ("business", 10, 0.250, [10.5]*14 + [16.0]*4 + [40.0] + [12.0]*4, 10.5, False),
]
for style, pg, gap, sizes, body, want_flag in REAL:
    t, h = thr(style, sizes, body)
    check(f"E5 {style} p{pg} gap={gap} heads={h} thr={t:.2f} → 적발={gap > t}",
          (gap > t) == want_flag, f"thr={t:.3f}")

# E6 반례 — 같은 면에서 표제만 걷어내면(=순수 공기) 다시 적발되어야 한다
for style, pg, gap, sizes, body, _ in REAL:
    flat = [body] * len(sizes)          # 표제 없는 동일 분량 면
    t, h = thr(style, flat, body)
    if gap > 0.18:
        check(f"E6 {style} p{pg} 표제 제거 시 재적발 (gap {gap} > 0.18)",
              h == 0 and gap > t, f"thr={t}")



# ============ F. tocgate 다면 목차 · 랩된 제목 행 (2026-08-16)
# 합성 PDF로 두 결함을 재현한다 — /tmp 렌더 픽스처는 휘발성이라 회귀 자산이 못 된다.
print("\n=== F. tocgate 목차 인식 ===")

import tocgate  # noqa: E402
try:
    import pymupdf as _fitz
except ImportError:
    import fitz as _fitz

F_TITLES = ["Alpha Governance Review", "Beta Electronic Voting",
            "Gamma Internal Control", "Delta Extremely Long Chapter Title For Wrapping"]
F_STARTS = [4, 8, 11, 14]          # 1-idx 장 시작 → offset 3 → 인쇄 기대 1,5,8,11


def make_toc_pdf(split=True, nums=(1, 5, 8, 11)):
    """앞붙이(표지+목차 1~2면) + 본문. split=False면 목차 1면에 전 장 수록.
    nums로 인쇄 쪽번호를 틀리게 심어 게이트 감도를 확인한다."""
    doc = _fitz.open()
    for _ in range(16):
        doc.new_page(width=420, height=595)
    doc[0].insert_text((60, 100), "Book Title", fontsize=20)

    def row(page, y, title, num, wrap=False):
        if wrap:   # 랩된 제목 — 쪽번호를 **둘째 줄**에 맞춘다(essay 조판 형태)
            page.insert_text((70, y), title[:22], fontsize=10)
            page.insert_text((70, y + 14), title[22:], fontsize=10)
            page.insert_text((370, y + 14), str(num), fontsize=10)
        else:
            page.insert_text((70, y), title, fontsize=10)
            page.insert_text((370, y), str(num), fontsize=10)

    if split:
        # 목차 1면: 1~3장 / 목차 2면(넘침): 4장 하나만 — 구 가드가 놓치던 형태
        for i, (t, n) in enumerate(zip(F_TITLES[:3], nums[:3])):
            row(doc[1], 150 + i * 40, t, n)
        row(doc[2], 150, F_TITLES[3], nums[3], wrap=True)
    else:
        for i, (t, n) in enumerate(zip(F_TITLES, nums)):
            row(doc[1], 150 + i * 40, t, n, wrap=(i == 3))
    # 도비라 — 장 시작 면에 장제목 재등장(확장이 본문으로 번지면 안 된다)
    for st, t in zip(F_STARTS, F_TITLES):
        doc[st - 1].insert_text((60, 120), t, fontsize=16)
    doc.set_toc([[1, t, st] for t, st in zip(F_TITLES, F_STARTS)])
    return doc


# F1 결함 A — 넘침 면에 장이 하나뿐이어도 목차로 인정
doc = make_toc_pdf(split=True)
old = tocgate.find_toc_pages(doc, F_TITLES)                       # ch_starts 없음(구 경로)
new = tocgate.find_toc_pages(doc, F_TITLES, ch_starts=F_STARTS)
check("F1a 구 경로(ch_starts 없음)는 넘침 면을 놓친다(회귀 기준선)", old == [1], f"old={old}")
check("F1b 신 경로는 목차 2면을 인정", new == [1, 2], f"new={new}")
a, pairs = tocgate.g14a_toc_numbers(doc, F_TITLES, F_STARTS)
check("F1c 다면 목차 G14-A PASS", not a, f"problems={a}")
check("F1d 4장 쌍 확보·인쇄=폴리오",
      len(pairs) == 4 and all(p["printed"] == p["expected"] for p in pairs),
      f"pairs={[(p['printed'], p['expected']) for p in pairs]}")
check("F1e 확장이 본문(도비라)까지 번지지 않음", max(new) < min(F_STARTS) - 1, f"new={new}")

# F2 결함 B — 쪽번호가 랩된 제목의 마지막 줄에 정렬돼도 찾는다
_sp = list(tocgate._spans(doc[2]))
_t = next(s for s in _sp if tocgate._norm(F_TITLES[3])[:10] in tocgate._norm(s["text"]))
band = tocgate._title_row_band(_sp, _t, F_TITLES[3])
check("F2a 랩된 제목 밴드가 둘째 줄까지 확장", band[1] - band[0] > 12, f"band={band}")
check("F2b 랩 제목의 쪽번호 11 페어링", any(p["printed"] == 11 for p in pairs),
      f"pairs={[(p['printed'], p['expected']) for p in pairs]}")

# F3 회귀 — 1면 목차는 종전대로
doc1 = make_toc_pdf(split=False)
one = tocgate.find_toc_pages(doc1, F_TITLES, ch_starts=F_STARTS)
a1, pairs1 = tocgate.g14a_toc_numbers(doc1, F_TITLES, F_STARTS)
check("F3a 1면 목차 인식 유지", one == [1], f"={one}")
check("F3b 1면 목차 G14-A PASS", not a1 and len(pairs1) == 4, f"problems={a1}")

# F4 감도 — 판정 기준은 안 건드렸다: 인쇄 쪽번호가 틀리면 여전히 FAIL.
#    넓힌 것은 "인식 범위"뿐이므로, 새로 보이게 된 넘침 면·랩 행에서도 오류는 잡혀야 한다.
bad1 = make_toc_pdf(split=True, nums=(99, 5, 8, 11))     # 목차 1면의 장
a2, _ = tocgate.g14a_toc_numbers(bad1, F_TITLES, F_STARTS)
check("F4a 목차 1면의 틀린 쪽번호 적발", any("인쇄 99" in x for x in a2), f"problems={a2}")
bad2 = make_toc_pdf(split=True, nums=(1, 5, 8, 77))      # 넘침 면의 랩된 장
a3, _ = tocgate.g14a_toc_numbers(bad2, F_TITLES, F_STARTS)
check("F4b 넘침 면·랩 행의 틀린 쪽번호도 적발", any("인쇄 77" in x for x in a3), f"problems={a3}")

for _d in (doc, doc1, bad1, bad2):
    _d.close()

# F5 실물 픽스처(있을 때만) — sub-typst 렌더본
_fx = Path("/tmp/bf-typo-fix")
_ran = False
for style in ("academic", "essay", "practical", "business", "base-academic"):
    pdf, outl = _fx / style / "draft" / "book.pdf", _fx / style / "outline.json"
    if not (pdf.exists() and outl.exists()):
        continue
    _ran = True
    t = [c["title"].strip() for c in json.loads(outl.read_text())["chapters"]]
    dd = _fitz.open(pdf)
    cs = sorted({p for l, _, p in dd.get_toc(simple=True) if l == 1})
    pa, _pr = tocgate.g14a_toc_numbers(dd, t, cs)
    pb = tocgate.g14b_key_color(dd, t, cs, None)
    tp = tocgate.find_toc_pages(dd, t, ch_starts=cs)
    check(f"F5 실물 {style} G14-A/B PASS (목차 {len(tp)}면)", not pa and not pb, f"A={pa} B={pb}")
    dd.close()
if not _ran:
    print("  [SKIP] F5 실물 픽스처 부재 — /tmp/bf-typo-fix")



# ============ G. tocgate 다면(3면 이상) 목차 · 시드 위치 · 절 행 충돌 (2026-08-17)
# 실서적(AIGP 12장·목차 5면)에서 시드가 목차 가운데 잡히고 **앞쪽 목차 면**이 통째로
# 누락돼 G14-A 4건이 났다. 장이 많으면 어느 면도 과반에 못 미친다는 것이 뿌리다.
print("\n=== G. tocgate 다면 목차·시드 위치·절 행 충돌 ===")

G_TITLES = [f"Chapter {c} Subject Matter" for c in
            ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot",
             "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima")]
G_STARTS = [6, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50]   # offset 5 → 인쇄 1,5,9,…


def make_multi_toc(layout, sections=()):
    """layout = 목차 면별 장 인덱스(0-based) 목록. sections = (면, y, 텍스트, 쪽번호).

    목차는 0-idx 1부터 연속 배치하고 본문은 G_STARTS(1-idx)에서 시작한다.
    """
    doc = _fitz.open()
    for _ in range(60):
        doc.new_page(width=420, height=595)
    doc[0].insert_text((60, 100), "Book Title", fontsize=20)
    for pi, chs in enumerate(layout):
        page = doc[1 + pi]
        for row, ci in enumerate(chs):
            y = 120 + row * 40
            page.insert_text((70, y), G_TITLES[ci], fontsize=10.5)          # 장 행
            page.insert_text((370, y), str(G_STARTS[ci] - 5), fontsize=10)  # 쪽번호
    for (pi, y, text, num) in sections:                                     # 절 행(9.5pt)
        doc[1 + pi].insert_text((110, y), text, fontsize=9.5)
        doc[1 + pi].insert_text((372, y), str(num), fontsize=9.5)
    for st, t in zip(G_STARTS, G_TITLES):                                   # 도비라
        doc[st - 1].insert_text((60, 120), t, fontsize=16)
    doc.set_toc([[1, t, st] for t, st in zip(G_TITLES, G_STARTS)])
    return doc


def toc_of(doc):
    return tocgate.find_toc_pages(doc, G_TITLES, ch_starts=G_STARTS)


# G1 시드가 가운데 면 — 앞뒤 양방향 확장이 모두 필요하다
mid = make_multi_toc([[0, 1], [2, 3, 4], [5, 6, 7, 8], [9, 10, 11]])
tp = toc_of(mid)
a, pairs = tocgate.g14a_toc_numbers(mid, G_TITLES, G_STARTS)
check("G1a 시드 가운데 — 목차 4면 전부 인식", tp == [1, 2, 3, 4], f"tp={tp}")
check("G1b 12장 G14-A PASS", not a, f"problems={a[:3]}")
check("G1c 12장 전부 인쇄=폴리오",
      len(pairs) == 12 and all(x["printed"] == x["expected"] for x in pairs),
      f"불일치={[(x['printed'], x['expected']) for x in pairs if x['printed'] != x['expected']]}")

# G2 시드가 마지막 목차 면 — 후방(앞쪽) 확장만으로 복원해야 한다
last = make_multi_toc([[0], [1, 2], [3, 4, 5], [6, 7, 8, 9, 10, 11]])
tp = toc_of(last)
a2, pairs2 = tocgate.g14a_toc_numbers(last, G_TITLES, G_STARTS)
check("G2a 시드 마지막 면 — 목차 4면 전부 인식", tp == [1, 2, 3, 4], f"tp={tp}")
check("G2b G14-A PASS", not a2 and len(pairs2) == 12, f"problems={a2[:3]}")

# G3 시드가 첫 면 — 전방 확장만 (구 동작 유지 확인)
first = make_multi_toc([[0, 1, 2, 3, 4, 5], [6, 7], [8, 9], [10, 11]])
tp = toc_of(first)
a3, _ = tocgate.g14a_toc_numbers(first, G_TITLES, G_STARTS)
check("G3a 시드 첫 면 — 목차 4면 전부 인식", tp == [1, 2, 3, 4], f"tp={tp}")
check("G3b G14-A PASS", not a3, f"problems={a3[:3]}")
check("G3c 확장이 본문(도비라)까지 안 번짐", max(tp) < min(G_STARTS) - 1, f"tp={tp}")

# G4 절 행 충돌 — 장 제목의 앞 10자를 품은 절 행이 장 행을 이기면 안 된다
#    (a) 앞면의 절 행 vs 뒷면의 장 행  (b) 장 행 바로 아래 절 행(밴드 삼킴)
coll = make_multi_toc(
    [[0, 1], [2, 3, 4], [5, 6, 7, 8], [9, 10, 11]],
    sections=[(1, 300, "Chapter India Subject Framework Overview", 3),   # ch9 키 선점(앞면)
              (2, 330, "Chapter Golf Subject", 7)])                      # ch7 부분문자열
a4, pairs4 = tocgate.g14a_toc_numbers(coll, G_TITLES, G_STARTS)
bad4 = [(x["title"][:22], x["printed"], x["expected"])
        for x in pairs4 if x["printed"] != x["expected"]]
check("G4a 절 행이 있어도 G14-A PASS", not a4, f"problems={a4[:3]}")
check("G4b 앞면 절 행이 장 행을 이기지 않음(ch9)", not bad4, f"불일치={bad4}")

# G5 밴드 삼킴 회귀 — 장 행 바로 아래 절 행이 제목의 접두사여도 밴드에 안 들어간다
#    (실서적 재현: 장 'Data Governance와 Model Training' / 절 'Data Governance')
_t = "Data Governance and Model Training"
_sp = [{"text": _t, "size": 10.5, "bbox": (111, 407, 276, 419)},
       {"text": "Data Governance", "size": 10.0, "bbox": (150, 423, 228, 435)}]
_band = tocgate._title_row_band(_sp, _sp[0], _t)
check("G5a 아래 절 행을 밴드에 삼키지 않음", _band[1] < 423, f"band={_band}")
_sp2 = [{"text": "Data Governance and", "size": 10.5, "bbox": (111, 407, 276, 419)},
        {"text": "Model Training", "size": 10.5, "bbox": (111, 423, 228, 435)}]
_band2 = tocgate._title_row_band(_sp2, _sp2[0], _t)
check("G5b 진짜 랩된 둘째 줄은 여전히 흡수", _band2[1] >= 435, f"band={_band2}")

# G6 감도 — 다면 목차에서도 틀린 쪽번호는 적발 (판정 기준 불변)
wrong = make_multi_toc([[0, 1], [2, 3, 4], [5, 6, 7, 8], [9, 10, 11]])
wrong[1].add_redact_annot(_fitz.Rect(360, 108, 400, 124), fill=(1, 1, 1))
wrong[1].apply_redactions()
wrong[1].insert_text((370, 120), "88", fontsize=10)      # ch1 쪽번호 오염
a5, _ = tocgate.g14a_toc_numbers(wrong, G_TITLES, G_STARTS)
check("G6 다면 목차의 틀린 쪽번호 적발", any("88" in x for x in a5), f"problems={a5[:2]}")

for _d in (mid, last, first, coll, wrong):
    _d.close()

# G7 실서적(있을 때만) — AIGP 12장·목차 5면 사본
_aigp = Path("/tmp/bf-aigp")
if (_aigp / "draft/book.pdf").exists():
    _t2 = [c["title"].strip() for c in json.loads((_aigp / "outline.json").read_text())["chapters"]]
    _dd = _fitz.open(_aigp / "draft/book.pdf")
    _cs = sorted({p for l, _, p in _dd.get_toc(simple=True) if l == 1})
    _tp = tocgate.find_toc_pages(_dd, _t2, ch_starts=_cs)
    _pa, _pp = tocgate.g14a_toc_numbers(_dd, _t2, _cs)
    _pb = tocgate.g14b_key_color(_dd, _t2, _cs, None)
    check(f"G7 실서적 AIGP G14-A/B PASS (12장, 목차 {len(_tp)}면)",
          not _pa and not _pb and len(_pp) == 12, f"A={_pa[:2]} B={_pb[:1]}")
    _dd.close()
else:
    print("  [SKIP] G7 실서적 사본 부재 — /tmp/bf-aigp")



# ============ H. G7 float 밀림 면제 복구 · 사유 코드 무결성 (2026-08-17)
# 계선+라벨 재설계 이후 콜아웃·표 경계가 0.3~1.2pt 헤어라인뿐이라 pagemetrics의
# `height > 2` 필터에 전부 걸려 _objs가 전권 0이 됐고, G7 float 면제가 죽었다.
print("\n=== H. G7 면제 복구 · role 무결성 ===")

import pagemetrics  # noqa: E402


# H1 괘선 블록 복원 — 순수 함수
def _r(y0, y1):
    return (y0, y1)


def _l(y0, size, n=20):
    return {"y0": y0, "y1": y0 + size * 1.08, "size": size, "text": "x" * n, "x1": 0}


# 콜아웃: 상단 0.6pt + 하단 0.3pt, 내부는 본문보다 작은 급수
blk = pagemetrics._rule_blocks([_r(100, 100.6), _r(260, 260.3)],
                               [_l(110, 9.5), _l(130, 9.5), _l(150, 9.5)], 10.0)
check("H1a 콜아웃 상/하 계선 사이가 한 블록", blk == [(100.0, 260.3)], f"{blk}")

# 두 블록이 본문을 사이에 두고 떨어져 있으면 병합하지 않는다(과대평가 = 면제 남발)
blk = pagemetrics._rule_blocks([_r(100, 100.6), _r(160, 160.3), _r(300, 300.6), _r(360, 360.3)],
                               [_l(110, 9.5), _l(200, 10.0), _l(230, 10.0), _l(320, 9.5)], 10.0)
check("H1b 사이에 본문이 끼면 별개 블록", blk == [(100.0, 160.3), (300.0, 360.3)], f"{blk}")

# 표(선 3개: 상단·머리·하단)는 급수가 같으므로 하나로 이어 붙인다
blk = pagemetrics._rule_blocks([_r(100, 101), _r(120, 120.4), _r(300, 301)],
                               [_l(105, 9.0), _l(130, 9.0), _l(200, 9.0)], 10.0)
check("H1c 선 3개짜리 표는 상단~하단 한 블록", blk == [(100.0, 301.0)], f"{blk}")

# 표(9pt) 바로 아래 콜아웃(9.5pt)이 붙어 있으면 급수 변화로 끊는다
blk = pagemetrics._rule_blocks([_r(100, 101), _r(200, 201), _r(220, 220.6), _r(340, 340.3)],
                               [_l(110, 9.0), _l(150, 9.0), _l(230, 9.5), _l(300, 9.5)], 10.0)
check("H1d 급수가 바뀌면 별개 블록(표 9pt → 콜아웃 9.5pt)",
      blk == [(100.0, 201.0), (220.0, 340.3)], f"{blk}")
check("H1e 선이 하나뿐이면 블록 없음", pagemetrics._rule_blocks([_r(100, 100.3)], [], 10.0) == [])
check("H1f 선이 없으면 블록 없음", pagemetrics._rule_blocks([], [], 10.0) == [])

# H2 얇은 괘선이 실제 PDF에서 살아 돌아오는가 — 근본 버그(height>2 필터) 회귀
_pdf = Path(tempfile.mkdtemp()) / "rules.pdf"
_d = _fitz.open()
for _ in range(3):
    _d.new_page(width=420, height=595)
_fr_mm = [26, 22, 34.9, 25]           # academic body_frame_mm
_MM = 72 / 25.4
_ft, _flx = _fr_mm[0] * _MM, _fr_mm[1] * _MM
_frx = 420 - _fr_mm[3] * _MM
for _pg in _d:
    for _k in range(12):          # 본문 급수가 최빈이 되도록 충분히
        _pg.insert_text((_flx, _ft + 200 + _k * 17.5), "body text line here " * 3, fontsize=10)
# 2면 상단에 0.3pt 전폭 괘선 2줄 + 그 사이 9.5pt 텍스트 = 통짜 콜아웃
_p2 = _d[1]
_p2.draw_line(_fitz.Point(_flx, _ft + 2), _fitz.Point(_frx, _ft + 2), width=0.3)
for _k in range(5):
    _p2.insert_text((_flx + 4, _ft + 20 + _k * 16), "callout body text", fontsize=9.5)
_p2.draw_line(_fitz.Point(_flx, _ft + 110), _fitz.Point(_frx, _ft + 110), width=0.3)
_d.save(str(_pdf)); _d.close()
_m = pagemetrics.analyze(_pdf, _fr_mm)
_blocks = _m["pages"][1]["_blocks"]
check("H2a 0.3pt 전폭 괘선 블록이 _blocks로 복원된다", len(_blocks) == 1, f"{_blocks}")
check("H2b 그 블록 높이가 괘선 간격과 일치", _blocks and abs((_blocks[0][1] - _blocks[0][0]) - 108) < 4,
      f"{_blocks}")
check("H2c _objs는 건드리지 않았다(reach·ink·G8 불변 보장)",
      all(not p["_objs"] for p in _m["pages"]), f"{[len(p['_objs']) for p in _m['pages']]}")

# H3 첫 결속 단위 소요 높이 — 통짜 블록 / H2 / H3 / 본문
_pitch, _body = 17.5, 10.0
_frame = (50.0, 73.7, 350.0, 538.9)
_mk = lambda lines, blocks=(): {"frame": _frame, "_lines": lines, "_objs": [],
                                "_blocks": list(blocks)}
_h = qc_gate.g7_first_unit_height(
    _mk([_l(80, 9.5)], [(73.7, 200.0)]), _pitch, _body)
check("H3a 통짜 블록 = 블록 높이 + 3행송 슬랙",
      _h is not None and abs(_h - (126.3 + 3 * _pitch)) < 1.0, f"{_h}")
_h2 = qc_gate.g7_first_unit_height(_mk([_l(74, 11.5), _l(200, 10.0)]), _pitch, _body, {"h2": 20.0})
check("H3b H2 절제목 = 제목 + 6행 결속 + 진입 여백",
      _h2 is not None and abs(_h2 - (11.5 * 1.08 + 6 * _pitch + 20.0)) < 1.0, f"{_h2}")
# 뒤 문단이 길면 §3 결속 하한 2행
_h3 = qc_gate.g7_first_unit_height(
    _mk([_l(74, 10.5)] + [_l(100 + k * _pitch, 10.0) for k in range(8)]),
    _pitch, _body, {"h3": 15.0})
check("H3c H3 소제목 = 제목 + 2행 결속 + 진입 여백",
      _h3 is not None and abs(_h3 - (10.5 * 1.08 + 2 * _pitch + 15.0)) < 1.0, f"{_h3}")
# 뒤 문단이 3행이면 고아/과부 2행 하한 탓에 쪼갤 수 없어 통째로 따라온다(p307 실사례)
_h3a = qc_gate.g7_first_unit_height(
    _mk([_l(74, 10.5), _l(100, 10.0), _l(100 + _pitch, 10.0), _l(100 + 2 * _pitch, 10.0)]),
    _pitch, _body, {"h3": 15.0})
check("H3c2 뒤 문단 3행이면 원자 — 결속 3행",
      _h3a is not None and abs(_h3a - (10.5 * 1.08 + 3 * _pitch + 15.0)) < 1.0, f"{_h3a}")
_h3b = qc_gate.g7_first_unit_height(_mk([_l(74, 10.5), _l(100, 10.0)]), _pitch, _body, {"h3": 15.0})
check("H3c3 뒤 문단 1행이어도 §3 하한 2행 아래로 안 내려간다",
      _h3b is not None and abs(_h3b - (10.5 * 1.08 + 2 * _pitch + 15.0)) < 1.0, f"{_h3b}")
# 리스트 항목은 원자 — 항목 전체 + 진입 여백, 결속 가산 없음
_hl = qc_gate.g7_first_unit_height(
    _mk([{"y0": 74, "y1": 84.8, "size": 10.0, "text": "• 첫 항목의 첫 줄", "x1": 0},
         {"y0": 74 + _pitch, "y1": 84.8 + _pitch, "size": 10.0, "text": "이어지는 줄", "x1": 0},
         {"y0": 74 + 2 * _pitch, "y1": 84.8 + 2 * _pitch, "size": 10.0, "text": "셋째 줄", "x1": 0}]),
    _pitch, _body, {"list": 7.0})
check("H3g 리스트 항목은 원자(항목 전체 + 진입 여백)",
      _hl is not None and abs(_hl - ((84.8 + 2 * _pitch - 74) + 7.0)) < 1.0, f"{_hl}")
check("H3h 번호 리스트도 인식",
      qc_gate.g7_first_unit_height(
          _mk([{"y0": 74, "y1": 84.8, "size": 10.0, "text": "4. 정답 ②. 해설", "x1": 0}]),
          _pitch, _body, {"list": 7.0}) is not None)
check("H3i 리스트가 아닌 본문 시작은 여전히 대상 아님",
      qc_gate.g7_first_unit_height(
          _mk([{"y0": 74, "y1": 84.8, "size": 10.0, "text": "평범한 본문 문장이다", "x1": 0}]),
          _pitch, _body, {"list": 7.0}) is None)
check("H3d 본문으로 시작하는 면은 면제 대상 아님",
      qc_gate.g7_first_unit_height(_mk([_l(74, 10.0), _l(95, 10.0)]), _pitch, _body) is None)
_hw = qc_gate.g7_first_unit_height(_mk([_l(74, 11.5), _l(90, 11.5), _l(200, 10.0)]),
                                   _pitch, _body, {"h2": 0.0})
check("H3e 2행으로 접힌 표제는 전체가 결속 단위",
      _hw is not None and _hw > 11.5 * 1.08 + 6 * _pitch, f"{_hw}")
check("H3f 표제가 면 위쪽이 아니면 대상 아님",
      qc_gate.g7_first_unit_height(_mk([_l(300, 11.5)]), _pitch, _body) is None)


# H4 refit — 꼬리 축과 중간면 축 분리 (③) + 자간 대역 (④)
import refit  # noqa: E402

_pg = lambda reach, lines, img=0.0: {"reach": reach, "lines": lines, "imgarea": img}
# 꼬리는 정상, 중간면 하나가 미달 — 예전엔 하나의 ok로 AND라 꼬리 해가 폐기됐다
_by = {1: _pg(0.95, 27), 2: _pg(0.62, 27), 3: _pg(0.95, 27), 4: _pg(0.88, 20)}
t_ok, m_ok, tr, tl, mm = refit.judge_chapter(_by, (1, 4), "academic", 27, None)
check("H4a 축 분리 — 꼬리 OK / 중간면 FAIL이 따로 나온다",
      t_ok is True and m_ok is False, f"tail={t_ok} mid={m_ok} mid_min={mm}")
_by2 = {1: _pg(0.95, 27), 2: _pg(0.95, 27), 3: _pg(0.30, 4)}
t2, m2, *_ = refit.judge_chapter(_by2, (1, 3), "academic", 27, None)
check("H4b 꼬리 6행 미만이면 꼬리 축 FAIL", t2 is False and m2 is True, f"tail={t2} mid={m2}")
_by3 = {1: _pg(0.95, 27), 2: _pg(0.95, 27), 3: _pg(0.95, 24)}
t3, m3, *_ = refit.judge_chapter(_by3, (1, 3), "academic", 27, None)
check("H4c 두 축 모두 통과", t3 is True and m3 is True, f"tail={t3} mid={m3}")
check("H4d 전면 도판 중간면은 중간면 축에서 제외",
      refit.judge_chapter({1: _pg(0.95, 27), 2: _pg(0.10, 2, img=0.9), 3: _pg(0.95, 24)},
                          (1, 3), "academic", 27, None)[1] is True)
check("H4e CAP_POS가 정본 ±15/1000em과 일치", refit.CAP_POS == 0.015, f"{refit.CAP_POS}")
check("H4f 양의 그리드가 그 대역까지 있다",
      max(refit.POS_GRID) == 0.015 and 0.0125 in refit.POS_GRID, f"{refit.POS_GRID}")
check("H4g refit MID_MIN이 qc_gate MID_ROLE_MIN과 동일",
      refit.MID_MIN == qc_gate.MID_ROLE_MIN, f"{refit.MID_MIN} vs {qc_gate.MID_ROLE_MIN}")

# H5 정본 동기화 — 사유 코드 7종 (⑤)
_pag = (REPO / "references/pagination.md").read_text(encoding="utf-8")
check("H5a pagination.md가 코드 7종으로 갱신됐다", "코드 7종" in _pag and "코드 6종" not in _pag)
check("H5b 7종 전부가 문서에 실재", all(c in _pag for c in qc_gate.ROLE_CODES),
      str([c for c in qc_gate.ROLE_CODES if c not in _pag]))
check("H5c 구현 ROLE_CODES가 7종", len(qc_gate.ROLE_CODES) == 7, str(len(qc_gate.ROLE_CODES)))



# ============ I. 판정 C 수리 — 표 폭 비례 · 이중 마커 · 도비라 (2026-08-17)
print("\n=== I. 판정 C 수리 ===")

# I1 (B-9) 표 컬럼 폭이 **내용 총량**에 비례한다
def _tbl(rows):
    md = "# 장\n\n" + "\n".join("| " + " | ".join(r) + " |" for r in rows[:1]) \
         + "\n| " + " | ".join("---" for _ in rows[0]) + " |\n" \
         + "\n".join("| " + " | ".join(r) + " |" for r in rows[1:]) + "\n"
    return tracks(md)

_short, _long = "용어", "이 항목은 상당히 긴 설명 문장을 담고 있어서 여러 행으로 접힌다"
# 용어 컬럼에 긴 항목이 **하나만** 있어도 예전엔 상한까지 부풀어 50:50이 됐다
_rev = _tbl([["구분", "설명"],
             ["Executive Leadership (CEO, COO, CRO, CDAO, CCO, CISO, CPO)", _long],
             [_short, _long], [_short, _long], [_short, _long], [_short, _long]])
_w = [int(x[:-2]) for x in _rev]
check("I1a 긴 항목 하나가 컬럼 전체를 부풀리지 않는다", _w[1] > _w[0], f"{_rev}")
check("I1b 내용 5배 차가 폭에 살아남는다(역전 없음)", _w[1] >= 2 * _w[0], f"{_rev}")

# 내용이 비슷하면 폭도 비슷 — 무회귀
_even = _tbl([["가", "나"], [_long, _long], [_long, _long]])
_we = [int(x[:-2]) for x in _even]
check("I1c 내용이 같으면 폭도 같다", _we[0] == _we[1], f"{_even}")
# 내용 1:2면 폭도 그 방향(판정이 정상이라 한 34:66·38:62 대역)
_ratio = _tbl([["가", "나"], [_long, _long + _long], [_long, _long + _long]])
_wr = [int(x[:-2]) for x in _ratio]
check("I1d 내용 1:2 → 폭도 1:2 방향", 1.2 <= _wr[1] / _wr[0] <= 2.2, f"{_ratio} 비={_wr[1]/_wr[0]:.2f}")
check("I1e 좁은 컬럼은 여전히 auto", tracks("# 장\n\n| 가 | 나 |\n| --- | --- |\n| 짧다 | 짧다 |\n")
      == ["auto", "auto"])

# I2 (B-5) 원문자 보기는 불릿 없이 — 이중 마커 제거
_quiz = md_to_typ("# 장\n\n- ① 첫 보기\n- ② 둘째 보기\n- ③ 셋째 보기\n")
check("I2a 원문자 리스트는 마커를 비운다", "#set list(marker: []);" in _quiz, _quiz[-160:])
check("I2b 리스트 문법 자체는 유지(되돌이 들여쓰기 보존)", "- ① 첫 보기" in _quiz)
_plain = md_to_typ("# 장\n\n- 평범한 항목\n- 또 다른 항목\n")
check("I2c 일반 리스트는 그대로", "marker: []" not in _plain, _plain[-90:])
_mixed = md_to_typ("# 장\n\n- ① 원문자 항목\n- 평범한 항목\n")
check("I2d 섞인 리스트는 건드리지 않는다", "marker: []" not in _mixed)
_hangul = md_to_typ("# 장\n\n- ㉮ 가 보기\n- ㉯ 나 보기\n")
check("I2e 한글 원문자도 인식(G16과 같은 범위)", "marker: []" in _hangul)
_ord = md_to_typ("# 장\n\n1. ① 번호 리스트\n2. ② 둘째\n")
check("I2f 번호 리스트는 대상 아님", "marker: []" not in _ord)

# I3 도비라 면 밀도 게이트
_fr = (50.0, 73.7, 350.0, 538.9)      # 하단 538.9pt
_op = lambda last_y: {"page": 8, "frame": _fr, "_objs": [], "_blocks": [],
                      "_lines": [{"y0": 100, "y1": 120, "size": 20.0, "text": "장 제목"},
                                 {"y0": last_y - 11, "y1": last_y, "size": 9.5, "text": "리드"}]}
_far = 538.9 - 70 * (72 / 25.4)       # 하단 공백 70mm
_near = 538.9 - 20 * (72 / 25.4)      # 하단 공백 20mm
check("I3a 별면 도비라(공백 70mm) → FAIL",
      len(qc_gate.g17_opener_check([_op(_far)], [8], "academic")) == 1)
check("I3b 본문이 흐르는 도비라(공백 20mm) → PASS",
      qc_gate.g17_opener_check([_op(_near)], [8], "academic") == [])
check("I3c 실측 근거 없는 스타일은 비대상(과잉 일반화 금지)",
      qc_gate.g17_opener_check([_op(_far)], [8], "essay") == []
      and qc_gate.g17_opener_check([_op(_far)], [8], "business") == [])
_blk = dict(_op(_near)); _blk["_blocks"] = [(300.0, 530.0)]
check("I3d 콜아웃·표도 하단 도달로 계산", qc_gate.g17_opener_check([_blk], [8], "academic") == [])
check("I3e 도비라가 아닌 면은 비대상", qc_gate.g17_opener_check([_op(_far)], [], "academic") == [])
check("I3f 정본에 G17이 기재됐다", "G17-OPENER" in _pag)



# ============ J. 2라운드 — 표 폭 붕괴 하한 · 행두 금칙 · 문항 10 (2026-08-17)
print("\n=== J. 2라운드 수리 ===")

# J1 (B-9 잔존) 최장 낱말 하한 — 폭이 낱말의 2배 미만이면 줄 채움이 붕괴한다
_lat = "Title VII of the Civil Rights Act, Americans with Disabilities Act (ADA)"
_kor = "주택의 매매·임대·금융에서 인수와 가격 양면에 모두 적용되며 각 주 보험법이 규율한다 " * 6
_t53 = _tbl([["분야", "적용 법령", "핵심 내용·사례"],
             ["Employment", _lat, _kor], ["Housing", _lat, _kor]])
_fr53 = [int(x[:-2]) for x in _t53 if x.endswith("fr")]
check("J1a 좁은 용어 컬럼은 auto, 나머지는 fr", _t53[0] == "auto" and len(_fr53) == 2, f"{_t53}")
check("J1b 내용 최대 컬럼이 가장 넓다", _fr53[-1] == max(_fr53), f"{_t53}")
check("J1c 라틴 컬럼이 낱말 붕괴 폭으로 눌리지 않는다",
      _fr53[0] / sum(_fr53) >= 0.15, f"{_t53}")
check("J1c2 내용 순서와 폭 순서가 어긋나지 않는다(단조성)", _fr53[0] <= _fr53[1], f"{_t53}")
check("J1d 끊을 수 없는 토큰 폭 — CJK는 어디서나 끊긴다",
      md2typ.unbreakable_width("Employment") == 10
      and md2typ.unbreakable_width("주택의 매매·임대") <= 2,
      f'{md2typ.unbreakable_width("Employment")} / {md2typ.unbreakable_width("주택의 매매·임대")}')
check("J1d2 raw 경로의 이스케이프가 낱말 폭을 부풀리지 않는다",
      md2typ.unbreakable_width('#raw("C:\\\\tmp\\\\foo")') == 10)
# 하한이 정상 비례를 덮지 않는다
_p12 = _tbl([["가", "나"], [_long, _long + _long], [_long, _long + _long]])
_wp = [int(x[:-2]) for x in _p12]
check("J1e 정상 비례는 하한에 눌리지 않는다", 1.2 <= _wp[1] / _wp[0] <= 2.2,
      f"{_p12} 비={_wp[1]/_wp[0]:.2f}")

# J2 (N-4) 행두 중점 금칙 — 문자는 그대로, 개행만 막는다
_wj = "\u2060"
_inl = md2typ.inline(md2typ.MD.parseInline("race · color 와 매매·임대")[0].children)
check("J2a 모든 가운뎃점 앞에 WORD JOINER", _inl.count(_wj) == _inl.count("·") == 2, repr(_inl))
check("J2b 가운뎃점 자체는 보존(표기 무변경)", "race \u2060· color" in _inl, repr(_inl))
check("J2c 폭 계산은 불변(형식문자 폭 0)",
      md2typ.visible_width(_inl) == md2typ.visible_width(_inl.replace(_wj, "")))
check("J2d 중복 삽입 없음", md2typ.no_break_interpunct(_inl) == _inl)
check("J2e 게이트 대조 정규화가 형식문자를 지운다",
      qc_gate.norm("race " + _wj + "· color") == "race·color"
      and tocgate._norm("race " + _wj + "· color") == "race·color")
check("J2f inline 밖 summary·caption도 공통 금칙 처리",
      md2typ.esc("리스크·모니터링") == "리스크" + _wj + "·모니터링")

# J3 (N-5) 문항 10 보기가 문항에 중첩된다
_q = md_to_typ("# 장\n\n9. 아홉?\n   - ① 가\n   - ② 나\n\n10. 열?\n    - ① 가\n    - ② 나\n")
_nested = _q.count("#set list(marker: []);")
check("J3a 문항 9·10 모두 보기 리스트가 중첩된다", _nested == 2, f"중첩 {_nested}개")
check("J3b 형제 리스트로 떨어지지 않는다", _q.count("+ 열?") == 1 and "\n- ① 가" not in _q, _q[-200:])
_bad = md_to_typ("# 장\n\n10. 열?\n   - ① 가\n")   # 3칸 = CommonMark상 형제
check("J3c 3칸 들여쓰기는 (정본대로) 중첩되지 않는다 — 원고 정규화가 필요한 이유",
      "+ 열?" in _bad and "#[" in _bad and _bad.index("#[") > _bad.index("+ 열?"), _bad[-140:])


print("\n" + "=" * 60)
print(f"PASS {len(OK)} / FAIL {len(FAIL)}")
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
    sys.exit(1)
print("ALL UNIT TESTS PASS")
