#!/usr/bin/env python3
"""bf-produce 집필 스웜 러너.

outline.json의 장마다 codex exec 워커를 병렬 스폰해 장 원고를 받고,
기계 계약 검사(H1 일치·금지 문법·이미지 경로)를 통과한 것만 chapters/에 반영한다.
워커는 read-only 샌드박스로 돌고(-o가 하니스 측에서 산출물을 받는다),
검증 실패 장은 위반 사유를 프롬프트에 붙여 재스폰한다.

기본 동작은 증분(chapters/에 없는 장만 집필). --only는 지목 장을 강제 재집필,
--all은 전 장 재집필. 결과는 out/swarm-report.json + 종료코드(전 장 통과 0)로 보고한다.
"""
import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
from pathlib import Path

# CommonMark 코드 펜스: ```/~~~ 3개 이상, 0~3칸 들여쓰기 허용, 닫는 펜스는 여는 것과
# 같은 종류·같은 길이 이상. 닫히지 않은 펜스는 문서 끝까지가 코드다.
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[^\n]*\n(?:.*?^ {0,3}\1[`~]*[ \t]*$|.*\Z)",
                      re.M | re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
HTML_RE = re.compile(r"<\s*/?[a-zA-Z][^>\n]*>")
IMG_RE = re.compile(r"!\[[^\]]*\]\(([^) \"]+)")

# ---- 표기 규범 (references/copyediting.md) ----
# 이 블록은 scripts/qc_gate.py의 G16과 **같은 규칙**이어야 한다. 갈라지면 스웜은
# 통과시키고 게이트는 반려하는 교착이 생긴다 — 임계·정규식 변경은 양쪽 동시에.
# 원문자 전 계열: ①-⑳·⑴-⒇·⒈-⒛·⒜-⒵·Ⓐ-Ⓩ·ⓐ-ⓩ·⓪-⓿ (U+2460~24FF) + 한글 ㉠-㉻ (U+3260~327B)
CIRCLED_RE = re.compile(r"[①-⓿㉠-㉻]")
PAREN_ENUM_RE = re.compile(r"(?<!\()\b\d{1,2}\)")  # 1) 2) 3)
LIST_ITEM_RE = re.compile(r"^(?:[-*+]|\d{1,2}[.)])\s")
TABLE_DELIM_RE = re.compile(r"^[\s:|-]+$")
EMDASH = "—"
EMDASH_MAX = 3
INLINE_OPTION_MSG = ("보기·선택지는 리스트 항목(- 또는 1.)으로 분리하라 "
                     "— 인라인 나열은 조판에서 줄바꿈되지 않는다")


def enum_count(s: str) -> int:
    """'N)' 나열 수 — 열린 괄호 안의 숫자는 제외한다.

    '(주 3) 참고, (표 4) 참고'는 보기 나열이 아니라 참조 표기다. 매치 지점까지의
    미결 여는 괄호 수가 양수면 괄호 안으로 보고 세지 않는다.
    """
    n = 0
    for m in PAREN_ENUM_RE.finditer(s):
        pre = s[:m.start()]
        if pre.count("(") - pre.count(")") > 0:
            continue
        n += 1
    return n


def option_count(s: str) -> int:
    return max(len(CIRCLED_RE.findall(s)), enum_count(s))


def table_line_idx(lines):
    """블록 안 GFM 표 영역의 줄 인덱스 — 구분행(`---|---`) 기준 위 1행(헤더)과 아래 연속 행.

    선행 `|` 유무는 GFM 표의 조건이 아니다. 구분행이 없으면 `|`로 시작해도 산문이다.
    """
    idx = set()
    for i, s in enumerate(lines):
        if "|" not in s or "-" not in s or not TABLE_DELIM_RE.match(s):
            continue
        idx.add(i)
        if i:
            idx.add(i - 1)  # 헤더 행
        j = i + 1
        while j < len(lines) and "|" in lines[j]:
            idx.add(j)
            j += 1
    return idx


def inline_option_lines(prose: str):
    """조판에서 한 덩어리로 접히는 보기 나열을 찾는다 (copyediting.md §4).

    마크다운은 문단 안의 단일 줄바꿈(softbreak)을 공백으로 접는다 — 보기를 리스트
    항목이 아닌 생줄로 나열하면 조판에서 줄바꿈 없이 이어진다. 그래서 줄이 아니라
    **문단**(빈 줄 구분) 단위로 합산하되, 정상 조판되는 리스트 항목·표 영역은 뺀다.
    리스트 항목 한 줄 안에 보기가 3개면 그 항목 자체가 덩어리이므로 따로 잡는다.
    """
    hits = []
    for block in re.split(r"\n\s*\n", prose):
        lines = [l.strip() for l in block.splitlines()]
        tbl = table_line_idx(lines)
        plain = []
        for i, s in enumerate(lines):
            if not s or i in tbl:
                continue  # 표 셀의 ①②③은 정상 조판 — 오탐 제외
            if LIST_ITEM_RE.match(s):
                if option_count(s) >= 3:
                    hits.append(s)  # 항목 한 줄에 보기 3개 = 그 항목이 덩어리
                continue
            plain.append(s)
        joined = " ".join(plain)
        if plain and option_count(joined) >= 3:
            hits.append(joined)
    return hits


def notation_problems(prose: str):
    """(하드 위반, 경고) — 인라인 보기 나열과 엠대시 남용."""
    violations, warnings = [], []
    hits = inline_option_lines(prose)
    if hits:
        violations.append(INLINE_OPTION_MSG + f" (위반 {len(hits)}곳: "
                          + "; ".join(repr(h[:40]) for h in hits[:2]) + ")")
    em = prose.count(EMDASH)
    if em > EMDASH_MAX:
        violations.append(f"엠대시 남용({em}개) — 삽입구는 괄호·쉼표로, 범위는 ~로 바꿔라")
    elif em:
        warnings.append(f"엠대시 {em}개 — 가능하면 줄여라")
    return violations, warnings


def extract_contract(skill_root: Path) -> str:
    """루트 SKILL.md에서 '## P1' 절 전문을 뽑는다 — 계약을 복제하지 않아 드리프트가 없다."""
    text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^## P1 .*?(?=^## )", text, re.M | re.S)
    if not m:
        sys.exit("FATAL: SKILL.md에서 '## P1' 절을 찾지 못했다 — 계약 추출 실패")
    return m.group(0).strip()


def strip_code(text: str) -> str:
    return INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))


def validate(text: str, title: str):
    """하드 위반 목록과 경고 목록을 돌려준다. 하드 위반이 있으면 반려."""
    violations, warnings = [], []
    text = text.strip()
    # 지시를 어기고 전체를 펜스로 감쌌으면 관용적으로 벗긴다
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```[^\n]*\n", "", text)[: -3].strip()
    lines = text.splitlines()
    if not lines:
        return ["원고가 비어 있다"], [], text
    if lines[0].strip() != f"# {title}":
        violations.append(f"첫 줄이 '# {title}'과 다르다 (실제: {lines[0][:60]!r})")
    h1s = [l for l in strip_code(text).splitlines() if l.startswith("# ")]
    if len(h1s) > 1:
        violations.append(f"H1이 {len(h1s)}개 — 파일당 1개만 허용")
    prose = strip_code(text)
    if any(l.startswith("####") for l in prose.splitlines()):
        violations.append("#### 이하 수준 제목 사용 — ###까지만 허용")
    if HTML_RE.search(prose):
        violations.append("HTML 태그 사용 — 계약 문법 밖 (코드블록 밖에서 발견)")
    for path in IMG_RE.findall(prose):
        if not path.startswith("../assets/"):
            violations.append(f"이미지 경로 위반: {path} — '../assets/'만 허용")
    nv, nw = notation_problems(prose)
    violations.extend(nv)
    warnings.extend(nw)
    return violations, warnings, text


def build_prompt(contract: str, ch: dict, brief: str, min_chars: int, max_chars: int,
                 feedback: str) -> str:
    parts = [
        "당신은 한국어 단행본의 한 장을 집필하는 작가다. 아래 계약·브리프에 따라 장 마크다운 전문을 작성하라.",
        "\n[콘텐츠 계약 — 이 문법만 사용한다]\n" + contract,
        f"\n[장 정보]\n- 파일: {ch['file']}\n- 제목: {ch['title']}\n- 요약(도비라에 실림): {ch.get('summary', '')}",
        "\n[장 브리프]\n" + (brief or "(브리프 없음 — 요약을 기준으로, 확인 불가한 수치·고유 사건 없이 일반 원리로 집필하라)"),
        "\n[출력 규칙]\n"
        f"- 최종 응답은 장 마크다운 전문만 담는다. 코드펜스로 감싸지 말고, 설명·인사를 붙이지 않는다.\n"
        f"- 첫 줄은 정확히 `# {ch['title']}`.\n"
        f"- 본문 분량 {min_chars:,}~{max_chars:,}자(공백 포함).\n"
        "- 브리프에 없는 수치·통계·고유 사건·인용문을 만들어 넣지 않는다. 근거가 없으면 일반 원리로 서술한다.\n"
        "- 이미지·도해는 브리프가 명시한 경우에만, `../assets/` 경로 단독 문단으로 쓴다.",
    ]
    if feedback:
        parts.append("\n[반려 사유 — 이전 시도가 다음 위반으로 반려되었다. 반드시 해소하라]\n" + feedback)
    return "\n".join(parts)


def spawn(cmd_base, prompt: str, out_path: Path, timeout: int):
    try:
        proc = subprocess.run(cmd_base + ["-o", str(out_path), "-"],
                              input=prompt, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stderr or "")[-2000:]
    except subprocess.TimeoutExpired:
        return -1, f"timeout {timeout}s"


def run_chapter(ch, args, contract, book_dir: Path, out_dir: Path):
    stem = Path(ch["file"]).stem
    brief_path = book_dir / "briefs" / ch["file"]
    brief = brief_path.read_text(encoding="utf-8") if brief_path.exists() else ""
    cmd_base = ["codex", "exec", "--skip-git-repo-check", "--ephemeral",
                "-s", "read-only", "-C", str(book_dir), "--color", "never"]
    if args.model:
        cmd_base += ["-m", args.model]
    record = {"chapter": ch["file"], "status": "fail", "attempts": [], "warnings": []}
    feedback = ""
    for attempt in range(1, args.retries + 2):
        prompt = build_prompt(contract, ch, brief, args.min_chars, args.max_chars, feedback)
        out_path = out_dir / f"{stem}.attempt{attempt}.md"
        if args.dry_run:
            print(f"[dry-run] {ch['file']}: brief={'있음' if brief else '없음'} "
                  f"prompt={len(prompt):,}자  cmd={' '.join(cmd_base)} -o {out_path} -")
            record["status"] = "dry-run"
            return record
        rc, err = spawn(cmd_base, prompt, out_path, args.timeout)
        if rc != 0 or not out_path.exists():
            record["attempts"].append({"n": attempt, "result": f"codex 실패 rc={rc}", "stderr": err})
            feedback = ""
            continue
        text = out_path.read_text(encoding="utf-8")
        violations, warnings, cleaned = validate(text, ch["title"])
        body_len = len(strip_code(cleaned))
        if not (args.min_chars * 0.8 <= body_len <= args.max_chars * 1.3):
            warnings.append(f"분량 {body_len:,}자 — 목표 {args.min_chars:,}~{args.max_chars:,}자 밖 (WARN)")
        record["attempts"].append({"n": attempt, "result": "pass" if not violations else "reject",
                                   "violations": violations})
        if not violations:
            (book_dir / "chapters" / ch["file"]).write_text(cleaned + "\n", encoding="utf-8")
            record["status"] = "pass"
            record["warnings"] = warnings
            record["chars"] = body_len
            return record
        feedback = "\n".join(f"- {v}" for v in violations)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("book_dir")
    p.add_argument("--skill", default=None, help="bookforge 스킬 루트 (기본: 이 스크립트 기준 자동 해석)")
    p.add_argument("--jobs", type=int, default=6, help="동시 워커 수 (orchestration.md: 6~15)")
    p.add_argument("--retries", type=int, default=2, help="장당 재스폰 횟수")
    p.add_argument("--timeout", type=int, default=1200, help="워커당 제한 초")
    p.add_argument("--min-chars", type=int, default=2000)
    p.add_argument("--max-chars", type=int, default=3000)
    p.add_argument("--model", default=None, help="codex -m 오버라이드")
    p.add_argument("--only", default=None, help="쉼표구분 장 지정(예: ch-02,ch-05) — 강제 재집필")
    p.add_argument("--all", action="store_true", help="전 장 강제 재집필")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    book_dir = Path(args.book_dir).resolve()
    skill_root = Path(args.skill).resolve() if args.skill else Path(__file__).resolve().parents[4]
    contract = extract_contract(skill_root)
    chapters = json.loads((book_dir / "outline.json").read_text(encoding="utf-8"))["chapters"]

    # 장 파일 유일성 — 워커는 stem으로 out/<stem>.attemptN.md를 쓰고 file로 chapters/에
    # 반영한다. 중복이면 두 워커가 같은 경로를 동시에 읽고 써서 한쪽이 다른 쪽 결과를
    # 검증하거나 마지막 쓰기가 앞선 결과를 덮는다. 병렬 진입 전에 막는다.
    files = [c["file"] for c in chapters]
    stems = [Path(f).stem for f in files]
    dup_files = sorted({f for f in files if files.count(f) > 1})
    dup_stems = sorted({s for s in stems if stems.count(s) > 1})
    if dup_files or dup_stems:
        sys.exit("FATAL: outline.json의 장 파일이 중복이다 — 워커 출력·chapters/ 쓰기가 충돌한다.\n"
                 f"  중복 file: {dup_files or '없음'}\n"
                 f"  중복 stem: {dup_stems or '없음'} (경로가 달라도 out/<stem>.attemptN.md가 겹친다)\n"
                 "  장마다 고유한 파일명을 쓸 것.")

    if args.only:
        want = {w.strip().removesuffix(".md") for w in args.only.split(",")}
        targets = [c for c in chapters if Path(c["file"]).stem in want]
    elif args.all:
        targets = chapters
    else:
        targets = [c for c in chapters if not (book_dir / "chapters" / c["file"]).exists()]
    if not targets:
        print("집필 대상 없음 (전 장 존재 — 재집필은 --only 또는 --all)")
        return

    out_dir = book_dir / "out"
    out_dir.mkdir(exist_ok=True)
    jobs = max(1, min(args.jobs, 15))
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        results = list(ex.map(lambda c: run_chapter(c, args, contract, book_dir, out_dir), targets))

    report = {"targets": len(targets), "passed": sum(r["status"] == "pass" for r in results),
              "results": results}
    (out_dir / "swarm-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in results:
        mark = {"pass": "OK", "dry-run": "--"}.get(r["status"], "FAIL")
        print(f"[{mark}] {r['chapter']} ({len(r['attempts'])}회 시도"
              + (f", {r.get('chars', 0):,}자" if r["status"] == "pass" else "") + ")")
        for w in r.get("warnings", []):
            print(f"       WARN: {w}")
    if not args.dry_run and report["passed"] < len(targets):
        sys.exit(1)


if __name__ == "__main__":
    main()
