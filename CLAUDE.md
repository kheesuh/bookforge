# bookforge — Claude Code 프로젝트 메모

저장소 안내는 [AGENTS.md](AGENTS.md), 파이프라인 정본은 [SKILL.md](SKILL.md).

## 하네스: 단권 전자책 제작

**목표:** 주제 한 줄 또는 완성 원고 → 상업도서급 PDF 1권. codex 집필 스웜(생성) + Claude 에이전트(검증·판정)의 분리 파이프라인.

**트리거:** 책·전자책·PDF 제작이나 그 후속(재빌드·게이트 수리·장 재집필·재판정) 요청 시 `bf-produce` 스킬을 사용하라. 스타일 팩·스크립트 등 저장소 자체 개발 작업과 단순 질문은 직접 처리한다.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-08-16 | 초기 구성 — 에이전트 4종(director·editor·fixer·judge) + bf-produce 오케스트레이터 + 스웜 러너 | 전체 | orchestration.md 스케치의 실체화 (codex 집필 + Claude 판정) |
| 2026-08-16 | 풀런 결함 9종 환류 — 교정교열 정본 신설(copyediting.md)·G16 게이트·러닝헤드 실측 말줄임·제목 여백 그리드·좌측바 콜아웃 전권 폐지·표 auto/fr 혼합·목차 grid 행·퀴즈 문법 | SKILL.md·styles/·templates/·scripts/·agents(editor·judge) | KH의 academic 풀런 실물 검수 피드백 |
