---
name: bf-produce
description: bookforge 저장소에서 전자책·PDF 책·책 조판·리포트 북 제작 요청(주제 한 줄이든 완성 원고든)을 받으면 반드시 이 스킬로 하네스를 실행한다. codex 집필 스웜 + Claude 검증·판정 에이전트로 책 1권을 생산하는 오케스트레이터. "책 만들어", "전자책으로", "북포지 돌려", "bookforge로 뽑아줘"는 물론 후속 요청 — "다시 빌드", "게이트 고쳐", "3장만 다시 써", "재판정 받아", "표지 스타일 바꿔서 재실행", "이전 책 이어서" — 에도 트리거된다. 스타일 팩·스크립트 개발 등 저장소 자체 수정 작업에는 트리거되지 않는다.
---

# bf-produce — 단권 제작 오케스트레이터

책의 "무엇을 어떻게"는 저장소 루트 `SKILL.md`(이하 정본)가 정의한다. 이 스킬은 "누가 언제"만 정의한다 — 정본의 P0~P5를 에이전트에 배정하고 순서를 강제한다. 정본과 이 스킬이 충돌하면 정본이 이긴다.

**실행 모드: 하이브리드** — 집필은 codex 스웜(프로세스 병렬·파일 계약), 검증·판정은 Claude 서브에이전트(`Agent` 도구, 반환값 수집). 에이전트 팀(SendMessage)은 쓰지 않는다: 집필 워커는 외부 프로세스라 팀에 참여할 수 없고, 나머지 단계는 순차 의존이라 팀 통신의 이득이 없다.

경로 규약: `<SKILL>` = 이 저장소 루트(bookforge). `<book_dir>` = 책 작업 디렉토리 — **반드시 저장소 밖**(AGENTS.md 규칙). 사용자가 지정하지 않으면 `~/books/<slug>`를 제안한다.

## Phase 0 — 컨텍스트 확인 (매 실행 첫 단계)

1. 정본 `SKILL.md`의 "실행 전 점검"을 수행한다(typst·pymupdf 등). codex CLI도 확인한다: `codex --version`. **codex가 없으면 중단하고 사용자에게 보고한다 — Claude가 대신 집필하는 폴백은 없다** (생성-검증 분리가 이 하네스의 정체성이다).
2. 실행 모드 판별:
   - `<book_dir>`가 없다 → **초기 실행** (P0부터)
   - `<book_dir>`가 있고 사용자가 부분 수정 요청 → **부분 재실행**: 요청을 단계에 매핑해 그 지점부터 재개 (장 재집필 → P1b `--only`, 게이트 수리 → P4, 재판정 → P5)
   - `<book_dir>`가 있고 새 책 요청 → 기존을 보존한 채 새 디렉토리로 **새 실행**
3. 진행 상태는 파일 실재로 판별한다: `outline.json` → `chapters/*.md` → `draft/book.pdf` → `final/*.pdf` 중 어디까지 있는가.

## 파이프라인 (담당 배정)

체크리스트를 복사해 진행하며 체크한다. 각 에이전트 호출은 `Agent` 도구 + 해당 `.claude/agents/` 정의 + `model: "opus"`.

```
[ ] P0  (메인) 모드·스타일·분량 확정 → scaffold.py — 정본 P0 절차 그대로
[ ] P1a (bf-content-director) topic: research.md + outline.json + briefs/ / manuscript: 인제스트~정규화 전부
[ ] P1b (codex 스웜 — topic 모드만) run_swarm.py → chapters/*.md
[ ] P1c (bf-copy-editor) 계약·사실·용어 검수 → 재스폰 목록 있으면 P1b를 --only로 반복 (최대 2회)
[ ] P2-3 (메인) build.py → draft/book.pdf
[ ] P4  (메인) qc_gate.py — FAIL이면 bf-gate-fixer 호출, PASS까지 (같은 게이트 3연속 실패 시 사용자 보고)
[ ] P5  (메인) contact_sheet.py → bf-style-judge 판정 — C면 위반 항목을 배정해 수리 후 재판정
[ ] 최종 (메인) 사용자 보고
```

세부 명령·완료 기준은 전부 정본과 modes/·references/가 정의한다. 이 스킬은 반복하지 않는다.

**P1b 스웜 실행:**

```bash
python3 <SKILL>/.claude/skills/bf-produce/scripts/run_swarm.py <book_dir> \
  --jobs 6 --min-chars 2000 --max-chars 3000        # 분량 대역은 length 프리셋에 맞춰 조정
# 재스폰: --only ch-02,ch-05  / 전 장 재집필: --all  / 사전 점검: --dry-run
```

스크립트가 계약 기계 검사(H1·금지 문법·이미지 경로)와 재스폰을 자체 처리한다. 종료코드 0이 아니면 `out/swarm-report.json`의 실패 장 사유를 확인하고, 브리프 결함이면 bf-content-director에게 해당 브리프 보강을 요청한 뒤 `--only`로 재실행한다.

**P5 판정 후 배정:** C 등급 위반 항목이 콘텐츠성(문장·용어·콜아웃 내용)이면 bf-copy-editor, 배치성(여백·겹침·쪽번호)이면 bf-gate-fixer에 배정한다. 수리 후 build→gate→contact_sheet를 다시 거쳐 재판정한다.

## 데이터 전달 프로토콜

파일 기반(산출물) + 반환값 기반(판정·처분) 조합. 에이전트 간 직접 통신은 없다 — 모든 인계는 `<book_dir>`의 파일과 메인의 반환값 중계로 한다.

| 경로 | 쓰는 쪽 → 읽는 쪽 |
|---|---|
| `research.md`, `outline.json`, `briefs/` | director → 스웜·editor |
| `out/*.attempt*.md`, `out/swarm-report.json` | 스웜 → 메인·editor |
| `chapters/*.md` | 스웜 → editor(교정 반영) → build |
| `gate-report.json`, `pageroles.json` | qc_gate → fixer |
| `qc/*.png` | contact_sheet → judge |

에이전트 호출 프롬프트에는 항상 `<SKILL>` 절대 경로, `<book_dir>` 절대 경로, 스타일 이름, 그리고 재호출이면 이전 반환 요약을 담는다.

## 에러 핸들링

| 상황 | 대응 |
|---|---|
| 실행 전 점검 실패 (typst·codex 부재 등) | 중단, 설치 요청 — 우회 진행 금지 |
| 스웜 장 실패 (retries 소진) | 브리프 보강(director) 후 `--only` 1회 → 그래도 실패면 실패 장 목록과 사유를 사용자 보고 |
| editor 재스폰 루프 2회 초과 | 남은 위반을 사용자에게 보고하고 판단을 받는다 |
| 같은 게이트 3연속 실패 | fixer의 원인 가설 첨부해 사용자 보고 (정본 규칙) |
| judge C 등급 2회 반복 | 위반 항목·수리 이력 첨부해 사용자 보고 |
| build.py 렌더 에러 | fixer가 아닌 메인이 로그를 읽고 원인(콘텐츠/환경) 분류 후 대응 |

공통 원칙: 1회 재시도 후 재실패면 누락을 명시하고 진행 가능한 데까지 진행한다. 산출물을 조용히 버리지 않는다 — `out/`·`_prev` 이력은 보존한다.

## 최종 보고 형식

① `final/<slug>.pdf` 경로 ② 게이트 요약(PASS 게이트 수, 수리 이력 유무) ③ judge 등급과 잔여 권고 ④ 스웜 통계(장 수·재스폰 횟수) ⑤ 검증 원장: 실행한 게이트·판정 에이전트, codex(집필)·Claude(검수) 분리 확인.

## 테스트 시나리오

**정상 흐름**: "AI 시대 법무팀 실무 가이드, short로 만들어줘" → P0에서 practical 선택·scaffold → director가 research+outline(6장)+briefs → 스웜 6장 병렬 집필(전 장 1회 통과) → editor 용어 통일 2건 교정 → build → gate PASS → judge B(권고 1건) → 최종 보고.

**에러 흐름**: 스웜에서 ch-04가 H1 불일치로 2회 반려 → 3회째 통과. gate에서 G7 꼬리 미달 FAIL → fixer가 refit.py로 해소 → PASS. judge가 C(차례 쪽번호 불일치, p.3 근거) → 배치성이므로 fixer 배정 → 수리·재빌드·재판정 A → 최종 보고에 수리 이력 명시.
