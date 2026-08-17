#!/usr/bin/env python3
"""G16 통합 검증 — 스크래치 미니 북에 qc_gate.py를 실제로 돌린다.

렌더 전 구간(G10 → G0 → G15-PARA → G16)까지의 동작으로 판정한다.
draft/book.pdf가 없으므로 정상 픽스처는 G16 통과 후 G1에서 멈추는 것이 기대값이다.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "qc_gate.py"

VIOLATING = """# 위반 장

이 장은 표기 규범을 어긴다. 근거는 — 비용 — 속도 — 신뢰 — 이렇게 넷이며 엠대시가 남용되었다.

퀴즈: 다음 중 옳은 것은?
① 첫 번째 보기
② 두 번째 보기
③ 세 번째 보기

정답은 본문에서 확인하라.
"""

CLEAN = """# 정상 장

이 장은 표기 규범을 지킨다. 삽입구는 괄호로 처리하고(이렇게), 범위는 3~5로 쓴다.

퀴즈: 다음 중 옳은 것은?

- ① 첫 번째 보기
- ② 두 번째 보기
- ③ 세 번째 보기

엠대시는 여기 — 한 번, 그리고 여기 — 두 번만 써서 WARN 구간에 머문다.

```text
코드블록 안 — — — — 엠대시 넷과 ① ② ③ 원문자는 검사 대상이 아니다
```

~~~text
틸드 펜스 안 — — — — 엠대시 넷과 ① ② ③ 원문자도 검사 대상이 아니다
~~~

근거는 (주 3) 참고, (표 4) 참고, (그림 5) 참고로 갈음한다.

항목 | 상태 | 결과
---|---|---
① 준비 | ② 실행 | ③ 검증
"""

# 결함 4 재현 — ①-⑳ 밖 원문자 계열도 잡혀야 한다
CIRCLED_ALT = """# 확장 원문자 장

보기를 한 문단에 이어 썼다. ㉮ 첫째 ㉯ 둘째 ㉰ 셋째.
"""


def make_book(root: Path, chapters: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root / "chapters").mkdir(exist_ok=True)
    (root / "book.json").write_text(json.dumps(
        {"title": "미니 북", "style": "academic", "length": "short"},
        ensure_ascii=False), encoding="utf-8")
    outline = {"chapters": []}
    for fname, (title, body) in chapters.items():
        (root / "chapters" / fname).write_text(body, encoding="utf-8")
        outline["chapters"].append({"file": fname, "title": title, "summary": "요약"})
    (root / "outline.json").write_text(json.dumps(outline, ensure_ascii=False),
                                       encoding="utf-8")


def run_gate(root: Path):
    r = subprocess.run([sys.executable, str(GATE), str(root)],
                       capture_output=True, text=True, cwd=str(REPO))
    rep = json.loads((root / "gate-report.json").read_text(encoding="utf-8"))
    return r, rep


OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


tmp = Path(tempfile.mkdtemp(prefix="bf-mini-"))
try:
    # ---- 1) 위반 픽스처 ----
    bad = tmp / "book-bad"
    make_book(bad, {"ch-01.md": ("위반 장", VIOLATING), "ch-02.md": ("정상 장", CLEAN)})
    r, rep = run_gate(bad)
    print("\n=== 위반 픽스처 stderr ===")
    print(r.stderr.strip())
    check("1a 종료코드 1", r.returncode == 1, f"rc={r.returncode}")
    check("1b G16.ok == False", rep["gates"]["G16"]["ok"] is False)
    check("1c G16 problems 2건(보기+엠대시)", len(rep["gates"]["G16"]["problems"]) == 2,
          str(rep["gates"]["G16"]["problems"]))
    check("1d fails가 G16 경로로 종료", all(f.startswith("G16:") for f in rep["fails"]),
          str(rep["fails"]))
    check("1e 실패 메시지에 기준 문서 포함",
          any("references/copyediting.md" in f for f in rep["fails"]))
    check("1f 렌더 전 선행 게이트 통과", rep["gates"]["G10"]["ok"] and rep["gates"]["G0"]["ok"]
          and rep["gates"]["G15-PARA"]["ok"])
    check("1g G1 미도달(렌더 전 차단)", "G1" not in rep["gates"], str(list(rep["gates"])))
    check("1h 정상 장의 엠대시 2개가 WARN에 기록",
          any("G16:" in w and "엠대시 2개" in w for w in rep["warns"]), str(rep["warns"]))

    # ---- 2) 정상 픽스처 ----
    good = tmp / "book-good"
    make_book(good, {"ch-01.md": ("정상 장", CLEAN)})
    r, rep = run_gate(good)
    print("\n=== 정상 픽스처 stderr ===")
    print(r.stderr.strip())
    check("2a G16.ok == True", rep["gates"]["G16"]["ok"] is True, str(rep["gates"]["G16"]))
    check("2b G16 problems 0 (틸드펜스·괄호참조·파이프없는표 오탐 없음)",
          rep["gates"]["G16"]["problems"] == [], str(rep["gates"]["G16"]["problems"]))
    check("2c G16 WARN 1건 기록", len(rep["gates"]["G16"]["warns"]) == 1,
          str(rep["gates"]["G16"]["warns"]))
    check("2d G16 통과 후 G1에서 멈춤(draft 없음)",
          rep["fails"] == ["G1: draft/book.pdf missing"], str(rep["fails"]))

    # ---- 3) 위반 없음 + 엠대시 0 → WARN도 0 ----
    quiet = tmp / "book-quiet"
    make_book(quiet, {"ch-01.md": ("무엠대시 장", "# 무엠대시 장\n\n엠대시 없는 평범한 문장이다.\n")})
    r, rep = run_gate(quiet)
    check("3a G16 통과 + WARN 0", rep["gates"]["G16"]["ok"] and rep["gates"]["G16"]["warns"] == [],
          str(rep["gates"]["G16"]))

    # ---- 3b) 결함 4 재현: 확장 원문자 계열 HARD ----
    alt = tmp / "book-alt"
    make_book(alt, {"ch-01.md": ("확장 원문자 장", CIRCLED_ALT)})
    r, rep = run_gate(alt)
    check("3b 한글 원문자 ㉮㉯㉰ 문단 → G16 FAIL", rep["gates"]["G16"]["ok"] is False
          and any("보기·선택지" in p for p in rep["gates"]["G16"]["problems"]),
          str(rep["gates"]["G16"]["problems"]))

    # ---- 4) 회귀: G16 도입 전 동작 유지 (G10 위반은 여전히 G10에서 잡힌다) ----
    g10 = tmp / "book-g10"
    make_book(g10, {"ch-01.md": ("G10 장",
                                 "# G10 장\n\n본문은 이 문장뿐이다.\n\n"
                                 "::: pull\n본문에 존재하지 않는 날조된 인용 문장이다\n화자\n:::\n")})
    r, rep = run_gate(g10)
    check("4a G10이 G16보다 먼저 차단", rep["gates"]["G10"]["ok"] is False
          and "G16" not in rep["gates"], str(list(rep["gates"])))

    # ---- 5) 사유 코드 무결성: 무효 선언이 G7 실패를 지우면 안 된다 (2026-08-17) ----
    # 실측 재현: role_by_page를 G11 검증과 무관하게 만들면 아무 코드나 찍어서 G7-MID/TAIL
    # soft 실패가 조용히 사라진다(보고 66 → 39로 위조). 총 판정은 G11 실패로 FAIL이지만
    # 보고 수치를 신뢰할 수 없게 된다.
    _FX = Path("/tmp/bf-typo-fix/academic")
    if (_FX / "draft/book.pdf").exists():
        import shutil as _sh
        _t = Path(tempfile.mkdtemp(prefix="bf-roles-"))
        _bd = _t / "book"
        _sh.copytree(_FX, _bd, ignore=_sh.ignore_patterns("qc", "final", "typeset"))
        (_bd / "pageroles.json").unlink(missing_ok=True)

        def _run(root):
            subprocess.run([sys.executable, str(GATE), str(root)],
                           capture_output=True, text=True, cwd=str(REPO))
            return json.loads((root / "gate-report.json").read_text(encoding="utf-8"))

        _base = _run(_bd)
        _g7 = lambda rep: sorted(x for x in rep.get("fails", []) if x.startswith("G7-"))

        # 중간면 전체에 아무 코드나 찍는다 — 전부 선행조건 위반이라 G11이 반려해야 한다
        _mid = [q["page"] for q in _base["metrics"]["pages"]
                if q["page"] not in _base["metrics"]["structural_exempt"]
                and q["page"] not in _base["metrics"]["tails"]][:6]
        (_bd / "pageroles.json").write_text(json.dumps({"roles": [
            {"page": pg, "code": "CH_CLOSE_APPROVED", "why": "무효 선언 실험",
             "anchor": None} for pg in _mid]}, ensure_ascii=False), encoding="utf-8")
        _bad = _run(_bd)

        check("5a 무효 선언 → G11 FAIL", _bad["gates"]["G11"]["ok"] is False,
              str(_bad["gates"]["G11"]["problems"][:2]))
        check("5b 무효 선언은 honored에 없다", _bad["gates"]["G11"].get("honored") == [],
              str(_bad["gates"]["G11"].get("honored")))
        check("5c 무효 선언이 G7 실패를 지우지 못한다", _g7(_bad) == _g7(_base),
              f"base={len(_g7(_base))}건 bad={len(_g7(_bad))}건")

        # 예산 초과는 선언 집합 전체를 무효화한다
        (_bd / "pageroles.json").write_text(json.dumps({"roles": [
            {"page": pg, "code": "PART_DIVIDER", "why": "예산 초과 실험", "anchor": None}
            for pg in range(2, 2 + max(4, int(0.08 * len(_base["metrics"]["pages"])) + 2))]},
            ensure_ascii=False), encoding="utf-8")
        _over = _run(_bd)
        check("5d 예산 초과 시 선언 전체 무효", _over["gates"]["G11"].get("honored") == [],
              str(_over["gates"]["G11"].get("honored")))
        check("5e 예산 초과에도 G7 수치 불변", _g7(_over) == _g7(_base),
              f"base={len(_g7(_base))}건 over={len(_g7(_over))}건")
        _sh.rmtree(_t, ignore_errors=True)
    else:
        print("  [SKIP] 5) 사유 코드 무결성 — 픽스처 부재")


finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "=" * 60)
print(f"PASS {len(OK)} / FAIL {len(BAD)}")
if BAD:
    for b in BAD:
        print("  FAILED:", b)
    sys.exit(1)
print("ALL INTEGRATION TESTS PASS")
