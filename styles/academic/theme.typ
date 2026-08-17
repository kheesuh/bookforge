// bookforge style: academic — 학술·논문형 (STYLE.md: 신국판 153×225, 1도+먹)
#import "base.typ": default-tokens, keep-words, chapter-state, fit-trunc
#import "base.typ" as base
#let code-font = ((name: "DejaVu Sans Mono", covers: regex("[A-Za-z0-9]")), "Pretendard")

#let meta = json("meta.json")

#let accent = rgb(meta.at("brand", default: "#12395F"))
#let accent-tint = rgb("#E8EDF3")
#let ink = rgb("#1A1A1A")
#let muted = rgb("#6E6E6E")
#let rule-c = rgb("#2E2E2E")

#let theme-tokens = default-tokens + (
  trim: (w: 153mm, h: 225mm),
  margin: (top: 26mm, bottom: 34.9mm, left: 25mm, right: 22mm),
  brand: accent, brand-light: accent-tint,
  ink: ink, muted: muted, paper: white,
  // Libertinus는 라틴 영숫자만 — covers 없이 1순위로 두면 한국어 문장의
  // 공백·쉼표·마침표까지 라틴 세리프로 빠진다 (code-font와 동일 클래스 버그)
  body-font: ((name: "Libertinus Serif", covers: regex("[A-Za-z0-9]")), "Noto Serif KR"),
  sans-font: ("Pretendard",),
  display-font: ("Pretendard",),
  body-size: 10pt,
)

#let TT = theme-tokens

// ---- 표지: 이중 룰 표제 블록, 타이포 전용 ------------------------------------
#let make-cover(meta) = {
  page(header: none, footer: none, {
    set par(justify: false, first-line-indent: 0em)
    v(48mm - 26mm)
    line(length: 100%, stroke: 1.2pt + accent)
    v(9mm)
    align(center, {
      text(font: TT.display-font, weight: "semibold", size: 28pt, tracking: -0.02em,
        fill: ink, keep-words(meta.title))
    })
    v(9mm)
    line(length: 100%, stroke: 0.4pt + rule-c)
    if meta.at("subtitle", default: none) != none {
      v(7mm)
      align(center, text(font: ("Noto Serif KR",), size: 13pt, fill: ink, keep-words(meta.subtitle)))
    }
    v(16mm)
    align(center, text(font: TT.display-font, weight: "medium", size: 11.5pt, fill: ink,
      meta.at("author", default: "bookforge")))
    v(1fr)
    align(center, text(font: TT.display-font, weight: "medium", size: 9.5pt, fill: ink,
      meta.at("publisher", default: "bookforge")))
  })
}

#let fig-counter = counter("bf-fig")
#let tbl-counter = counter("bf-tbl")
// 표 라벨 → 그 표가 시작한 면. 분할 표의 (계속) 판별용.
#let tbl-start = state("bf-tbl-start", (:))

// ---- 장 헤더: 도비라 별면 금지 — 같은 면에서 본문 시작 ------------------------
#let bf-chapter(title, summary: none) = {
  pagebreak(weak: true)
  chapter-state.update(s => (num: s.num + 1, title: title))
  counter(heading).step(level: 1)
  tbl-counter.update(0)
  fig-counter.update(0)
  context {
    let n = chapter-state.get().num
    v(12mm)
    hide(block(height: 0pt, heading(level: 1, outlined: true, bookmarked: true, numbering: none, title)))
    v(-1.2em)
    text(font: TT.display-font, weight: "medium", size: 10pt, tracking: 0.15em,
      fill: accent, "제" + str(n) + "장")
    v(4mm)
    line(length: 18mm, stroke: 1pt + accent)
    v(7mm)
    text(font: TT.display-font, weight: "semibold", size: 20pt, fill: ink, keep-words(title))
    v(8mm)
    line(length: 100%, stroke: 1pt + ink)
    if summary != none {
      v(9mm)
      block({
        set text(font: ("Noto Serif KR",), size: 9.5pt, fill: muted)
        set par(leading: 6.5pt, first-line-indent: 0em, justify: true)
        summary
      })
    }
    v(12mm)
  }
}

// ---- 정의·정리 박스 ----------------------------------------------------------
// 학술서 관행인 **상하 먹 계선 + 라벨**. 색면(accent-tint 배경)과 좌측 세로바는
// 쓰지 않는다 — 단행본·학술서 조판 관행이 아니고, 본문 무채색 비율(§9)도 깨뜨린다.
#let bf-callout(kind: "info", title: none, body) = {
  // quote(= md2typ의 ::: quote / ::: pull)는 라벨을 붙이지 않는다 — 인용에 "정리"
  // 라벨이 붙던 결함. 라벨이 별행으로 올라오면서 더 두드러진다.
  let label = if title != none { title }
    else if kind == "warn" { "유의" }
    else if kind == "quote" { none }
    else { "정리" }
  block(
    // **분할 가능(breakable)** — 콜아웃이 통짜였을 때 장 첫 블록(학습 목표)이
    // 도비라 잔여 공간(9~84mm)보다 커서(67~130mm) 통째로 이월했고, 그 결과
    // 12개 장 중 7개가 본문 0행짜리 별면 도비라가 됐다(판정 C-1, 실측).
    // 계선+라벨 문법에서는 조각이 표 분할과 같은 꼴(상단 계선-내용-하단 계선)로
    // 읽히므로 색면 박스 시절의 불가분성 전제가 더는 필요 없다.
    width: 100%, breakable: true,
    // B4(주의/경고)는 상단 계선 1.2pt — book-anatomy §10
    stroke: (top: (if kind == "warn" { 1.2pt } else { 0.6pt }) + ink,
             bottom: 0.3pt + ink),
    inset: (x: 0pt, top: 5pt, bottom: 6pt), above: 5mm, below: 5mm,
    {
      set text(size: 9.5pt)
      set par(leading: 6.5pt, first-line-indent: 0em)
      if label != none {
        // sticky — 분할 시 라벨만 앞 면에 홀로 남는 것을 막는다
        block(sticky: true, above: 0pt, below: 0pt,
          text(font: TT.sans-font, weight: "semibold", size: 9pt, tracking: 0.05em,
            fill: if kind == "warn" { rgb("#8C2B20") } else { ink }, label))
        v(3pt, weak: true)
      }
      body
    })
}

// 값·라벨은 굵기와 급수로 가른다 — 엠대시 구분자를 쓰지 않는다
#let bf-stat(value, label) = bf-callout(title: "수치")[
  #strong(value)#h(0.8em)#text(size: 9pt, fill: muted, label)
]

#let bf-fig(path, caption: none, source: none, width: 100%) = {
  // placement: bottom — 도해를 면 하단으로 부동시켜 본문이 면을 계속 채우게 한다.
  // 인라인 블록이면 도해+후속 제목이 통째로 이월해 앞 면이 반백이 되고(G7-MID),
  // top 부동이면 꼬리면 reach가 도해 높이에서 캡되어 G7-TAIL에 걸린다.
  figure(placement: bottom, kind: image, supplement: none, numbering: none, gap: 0mm,
    block(breakable: false, above: 5mm, below: 5mm, {
    align(center, image(path, width: width))
    context {
      fig-counter.step()
      let n = chapter-state.get().num
      let f = fig-counter.get().first() + 1
      if caption != none {
        v(2mm)
        align(center, {
          set text(font: TT.sans-font, size: 8.5pt)
          text(weight: "semibold", fill: accent, "[그림 " + str(n) + "-" + str(f) + "] ")
          text(fill: ink, caption)
          if source != none { text(fill: muted)[ (자료: #source)] }
        })
      }
    }
  }))
}

// 표: 콘텐츠가 [표] 캡션을 준 경우에만 번호 라벨. 캡션 없으면 표만 렌더.
// 표는 분할 가능(breakable) — 통짜 표는 남은 공간보다 크면 통째로 이월해 앞 면에
// 구멍을 내고(G7), 면보다 크면 하단이 판면 밖으로 넘쳐 글자가 뭉개진다(G3).
// 분할 시 각 조각은 booktabs 3선을 온전히 갖는다: 상단 1.0pt + 반복 머리 행 +
// 머리 아래 0.4pt + 하단 1.0pt(래퍼 stroke가 조각마다 그린다 — longtable 관행).
#let bf-tbl(caption: none, source: none, body) = block(breakable: true, above: 6mm, below: 6mm, width: 100%, {
  // 캡션·자료·표는 모두 **좌단 기준 좌측 정렬** — 규정 "표 캡션은 표 폭 기준 좌측 정렬"
  // (구판은 셋 다 판면 정중앙이었다: 판정 B-1·B-2). 표 자체도 좌측 정렬로 맞춰야
  // 폭이 좁은 auto 표에서 캡션 좌단과 표 좌단이 어긋나지 않는다.
  // 전역 par(first-line-indent: all)이 캡션·자료를 1자 밀어내므로 여기서 해제한다
  // (해제 전 실측: 캡션 x=80.9pt / 자료 78.9pt vs 판면 좌단 70.9pt).
  set par(first-line-indent: 0em)
  if caption != none {
    context {
      tbl-counter.step()
      let n = chapter-state.get().num
      let m = tbl-counter.get().first() + 1
      let lab = "표 " + str(n) + "-" + str(m)
      // 이 표가 시작한 면을 기록해 둔다 — 반복 머리 행에서 "이어짐" 판별에 쓴다.
      // here()는 update 클로저 밖에서 미리 풀어야 한다(클로저는 context 밖에서 실행됨)
      let start-pg = here().page()
      tbl-start.update(d => { let e = d; e.insert(lab, start-pg); e })
      // 라벨 Pretendard SemiBold 9pt + 1자 공백 + 제목 Noto Serif KR 9pt (규정)
      text(font: TT.sans-font, size: 9pt, weight: "semibold", fill: accent, lab + ".")
      h(1em)
      text(font: ("Noto Serif KR",), size: 9pt, fill: ink, caption)
      v(2mm)
      // (계속) 표기 — 반복 머리 행 안의 context는 **조각마다 재평가된다**(실측 확인).
      // 그래서 조각의 면 > 표 시작 면이면 이어짐으로 판별할 수 있다. 표 위쪽에
      // 얹지 않고 머리 행 첫 칸에 붙이는 이유: 이어짐 조각은 판면 상단에서 시작해
      // 표 위에 여백이 없다(그 자리는 러닝헤드 헤어라인 영역).
      show table.cell.where(y: 0): it => if it.x != 0 { it } else {
        context {
          if here().page() > tbl-start.get().at(lab, default: 0) {
            // place로 얹어 행 높이를 늘리지 않는다 — 셀 안에 인라인으로 넣으면
            // 좁은 첫 칼럼에서 줄바꿈돼 머리 행만 2행이 되고 옆 칸 세로 정렬이 틀어진다.
            // 이어짐 조각은 판면 상단에서 시작하므로 표 상단 룰 위 여백에 앉힐 수 있다.
            place(top + left, dy: -4.2mm,
              text(font: TT.sans-font, size: 7.5pt, weight: "regular", fill: muted,
                lab + " (계속)"))
          }
          it
        }
      }
      block(stroke: (bottom: 1pt + ink), inset: 0pt, body)  // booktabs bottomrule
      if source != none {
        v(2mm)
        text(font: TT.sans-font, size: 8pt, fill: muted, [자료: #source])
      }
    }
  } else {
    block(stroke: (bottom: 1pt + ink), inset: 0pt, body)
    if source != none {
      v(2mm)
      text(font: TT.sans-font, size: 8pt, fill: muted, [자료: #source])
    }
  }
})

// ---- 목차 보조: 제목에 이미 박힌 번호를 뽑아낸다(중복 표기 방지) --------------
#let bf-plain(c) = {
  if c == none { "" }
  else if type(c) == str { c }
  else if type(c) == content {
    if c.has("text") { c.text }
    else if c.has("children") { c.children.map(bf-plain).fold("", (a, b) => a + b) }
    else if c.has("body") { bf-plain(c.body) }
    else { "" }
  } else { "" }
}

// "1.2 제목" → ("1.2", "제목") / 번호가 없으면 (none, 원문)
#let bf-split-num(s) = {
  let m = s.match(regex("^\s*([0-9]+(?:[.\-][0-9]+)*)[.)]?[ \t]+(.+)$"))
  if m == none { (none, s) } else { (m.captures.at(0), m.captures.at(1)) }
}

#let colophon(meta, t) = {
  pagebreak(weak: true)
  page(header: none, footer: none, {  // 판권면: 러닝헤드·쪽번호 생략(러닝 시스템 규약)
    set text(font: TT.display-font, size: 8.5pt, fill: ink)
    set par(leading: 4.5pt, first-line-indent: 0em)
    v(1fr)
    meta.title
    // 부제는 별행 — 엠대시 연결 표기를 쓰지 않는다
    if meta.at("subtitle", default: none) != none { linebreak(); meta.subtitle }
    linebreak()
    [#meta.at("date", default: "") 발행 · 지은이 #meta.at("author", default: "bookforge")]
    linebreak()
    [조판 bookforge · 본문 Noto Serif KR·Libertinus Serif · 표제 Pretendard]
  })
}

// ---- 마스터 래퍼 -------------------------------------------------------------
#let book(meta: (:), tokens: (:), cover: none, toc: true, toc-title: "차 례", body) = {
  let t = TT
  set document(title: meta.at("title", default: "무제"), author: meta.at("author", default: "bookforge"))
  set page(
    width: t.trim.w, height: t.trim.h,
    margin: (top: t.margin.top, bottom: t.margin.bottom, left: t.margin.left, right: t.margin.right),
    header: context {
      let prev = query(heading.where(level: 1).before(here()))
      // 장 시작 면(도비라)은 러닝헤드 생략
      let starts = query(heading.where(level: 1)).map(h => h.location().page())
      if prev.len() > 0 and not starts.contains(here().page()) {
        // 러닝헤드 급수 = 본문 × 0.8 = 8pt (book-anatomy §8)
        set text(font: t.sans-font, size: 8pt, weight: "medium", fill: ink)
        // 전역 par(first-line-indent all:true)가 머릿말까지 1자 밀어내는 것을 차단
        set par(first-line-indent: 0em, justify: false, leading: 0.5em)
        // 좌(장) · 우(절)를 판면 폭의 고정 비율로 나눈 칼럼에 넣는다. 자수 기준
        // 절단은 자폭 차이 탓에 폭을 보장하지 못해 두 텍스트가 한 줄에서 충돌했다
        // (실측: 106mm 판면에서 2행으로 흘러넘침). 이제 각 칼럼 안에서
        // fit-trunc가 **실측 폭** 기준으로 말줄임하므로 겹침이 구조적으로 불가능하다.
        let fw = t.trim.w - t.margin.left - t.margin.right  // 판면 폭 106mm
        let lw = fw * 0.58
        let rw = fw * 0.38
        // 우측: 현재 장 안에서 진행 중인 절만 (경계 오류 방지 — 이전 장 절 참조 금지,
        // 현재 면에서 시작한 절 포함, 절이 없으면 항목 생략)
        let ch-pg = prev.last().location().page()
        let secs = query(heading.where(level: 2)).filter(s => {
          let sp = s.location().page()
          sp >= ch-pg and sp <= here().page()
        })
        grid(columns: (lw, 1fr, rw), rows: (auto,),
          context {
            // 번호는 항상 보존, 제목 꼬리만 말줄임
            let pre = "제" + str(prev.len()) + "장"
            let pw = measure(text(fill: accent, pre)).width
            text(fill: accent, pre)
            h(10pt)
            fit-trunc(bf-plain(prev.last().body), lw - pw - 12pt)
          },
          [],
          if secs.len() > 0 {
            align(right, context {
              let num = str(prev.len()) + "." + str(secs.len()) + " "
              // B-10: 헤드는 --ink (구판 우측 절 칼럼만 --muted였다)
              let nw = measure(num).width
              num
              fit-trunc(bf-plain(secs.last().body), rw - nw - 2pt)
            })
          } else { [] })
        v(1.5mm)
        line(length: 100%, stroke: 0.4pt + rule-c)
      }
    },
    // B-8: 쪽번호는 Libertinus Serif 9pt tabular (규정 §러닝 시스템). 구판은 Pretendard.
    footer: context align(center,
      text(font: t.body-font, size: 9pt, fill: ink,
        number-type: "lining", number-width: "tabular",
        str(counter(page).get().first()))),
  )
  // 행송 17.5pt 고정: top/bottom-edge 고정 + leading 7.5pt
  set text(font: t.body-font, size: 10pt, fill: ink, lang: "ko", region: "KR",
    top-edge: 0.8em, bottom-edge: -0.2em, hyphenate: false,
    number-type: "lining", number-width: "tabular")
  set text(costs: (orphan: 100%, widow: 100%, runt: 200%))
  set par(justify: true, leading: 7.5pt, spacing: 7.5pt,
    first-line-indent: (amount: 1em, all: true))

  set heading(numbering: (..n) => {
    let p = n.pos()
    if p.len() >= 2 { p.slice(1).map(str).join(".") } else { none }
  })
  // 표제 위아래 여백은 행송(17.5pt)의 배수 — book-anatomy §6.3/§6.4
  // 절(H2) 위 2행(35pt) + 아래 1행(17.5pt), 항(H3) 위 1.5행(26.25pt) + 아래 0.5행(8.75pt).
  // 종전 값(H2 아래 8.75pt / H3 아래 5pt)은 par spacing 7.5pt에 흡수돼 제목이
  // 본문에 붙어 보였다.
  show heading.where(level: 2): it => {
    v(35pt, weak: true)
    block(sticky: true, text(font: t.sans-font, size: 11.5pt, weight: "semibold", fill: ink, {
      counter(heading).display((..n) => str(chapter-state.get().num) + "." + str(n.pos().at(1, default: 1)))
      h(1.5em)
      it.body
    }))
    v(17.5pt, weak: true)
  }
  show heading.where(level: 3): it => {
    v(26.25pt, weak: true)
    block(sticky: true, text(font: t.sans-font, size: 10.5pt, weight: "medium", fill: ink, it.body))
    v(8.75pt, weak: true)
  }

  show quote.where(block: true): it => block(
    inset: (left: 2em, right: 1em), above: 6mm, below: 6mm, {
      set text(size: 9.5pt)
      set par(leading: 6.5pt, first-line-indent: 0em)
      it.body
    })
  // B-4: 불릿은 `–`(en dash) — 중점 `·`는 klreq 구분 부호와 충돌(규정 §목록)
  set list(marker: ([–], [·]), indent: 1em, spacing: 7.5pt)
  // B-6: 번호 목록은 `1) 2) 3)` (규정 §목록)
  set enum(numbering: "1)", indent: 1em, spacing: 7.5pt)
  show raw.where(block: true): it => block(
    width: 100%, fill: luma(248), inset: 8pt, above: 5mm, below: 5mm,
    text(font: code-font, size: 8.5pt, it))

  // 3선표(booktabs): 상하 1.0pt 먹, 헤더 아래 0.4pt. 캡션은 콘텐츠 [표] 계약(bf-tbl)만
  set table(stroke: none, inset: (x: 8pt, y: 5pt))
  show table: it => { set text(size: 9pt, font: t.sans-font); it }
  // booktabs 3선: top 1.0 / 헤더 아래 0.4 / bottom 1.0 (bottom은 bf-tbl 래퍼가 긋는다)
  // 헤더 아래 룰은 **머리 행의 bottom**으로 건다(구판은 다음 행의 top이었다) —
  // 표가 분할되면 반복된 머리 행 셀의 y는 0이지만 그 아래 본문 행은 y가 1이 아니라
  // 이어지는 번호라, top: y==1 방식은 뒷조각에서 머리 아래 룰이 사라진다(실측).
  set table(stroke: (x, y) => (
    top: if y == 0 { 1pt + ink } else { none },
    bottom: if y == 0 { 0.4pt + rule-c } else { none },
  ))
  show table.cell.where(y: 0): it => text(weight: "semibold", it)
  show table.cell: set par(justify: false)  // 셀 양끝맞춤 파열 방지
  show table.cell: set align(left + horizon)  // 왼끝맞춤(가운데 정렬 금지)
  show link: it => text(fill: accent, it)

  if cover != none { cover }
  // 속표지
  page(header: none, footer: none, {
    v(44mm)
    line(length: 100%, stroke: 0.4pt + rule-c)
    v(7mm)
    align(center, text(font: t.display-font, weight: "semibold", size: 20pt, keep-words(meta.title)))
    if meta.at("subtitle", default: none) != none {
      v(5mm)
      align(center, text(font: ("Noto Serif KR",), size: 11pt, meta.subtitle))
    }
    v(10mm)
    align(center, text(font: t.display-font, weight: "medium", size: 10pt, meta.at("author", default: "")))
  })
  if toc {
    // 앞붙이 쪽번호(i, ii, iii…) · 러닝헤드 없음
    counter(page).update(1)
    // 목차 1행 = [들여쓰기] + 번호칼럼 14mm + 제목(1fr) + 쪽번호 9mm(우측).
    // 리더 점선 없음. 행송 16pt: em 박스가 1em으로 고정(top-edge .8em /
    // bottom-edge -.2em)돼 있으므로 블록 간격 6pt + 본문 10pt = 16pt,
    // 되돌이 줄도 leading 6pt로 같은 행송을 쓴다.
    //
    // **구조를 grid로 두는 이유(회귀 방지)**: 종전 구현은 한 문단 안에서
    // `h(indent)` + 번호 박스 + 제목 + `h(1fr)` + 쪽번호 박스를 늘어놓고
    // 되돌이 줄을 `hanging-indent`로 당겼다. 그런데 `h(1fr)`이 낀 문단에서는
    // 되돌이 줄이 hanging-indent를 잃고 **판면 왼쪽 끝까지 탈출한다**(실측:
    // 40자 장 제목의 둘째 줄이 번호 칼럼 밖으로 나가고, tocgate G14-A가
    // 그 행의 쪽번호를 못 찾아 FAIL). 칼럼을 grid로 만들면 되돌이 줄이
    // 제목 셀 안에 머무는 것이 **문단 설정이 아니라 구조**가 된다.
    //
    // 정렬: 세 칼럼 모두 top — 번호·제목·쪽번호가 **첫 줄에서** 베이스라인을 맞춘다.
    // (쪽번호를 bottom으로 두어 마지막 줄에 붙이면 tocgate G14-A가 제목 첫 줄과
    //  y가 겹치는 숫자 스팬만 쪽번호로 인정하므로 2행 제목에서 FAIL한다 —
    //  tocgate.py:144-151. 항목의 시작 줄에 쪽번호를 다는 편이 목차 관행에도 맞다.)
    // 세 텍스트 모두 전역 em 박스(top .8em / bottom -.2em)를 그대로 쓴다.
    // fill을 text()로 직접 박는 이유: 전역 `show link: 별색` 규칙을 안쪽에서 덮기 위함.
    let toc-row(loc, indent: 0mm, num: none, num-font: none, num-fill: ink,
                title: none, page-no: none,
                size: 10pt, weight: "regular", above: 6pt, sticky: false) = block(
      width: 100%, above: above, below: 0pt, sticky: sticky,
      {
        set par(first-line-indent: 0em, hanging-indent: 0em,
          leading: 16pt - size, spacing: 0pt, justify: false)
        grid(
          columns: (indent, 14mm, 1fr, 9mm),
          rows: (auto,),
          align: (left + top, left + top, left + top, right + top),
          [],
          // box로 감싸 번호가 14mm를 넘어도(제10장 등) 셀 안에서 줄바꿈되지 않게 한다
          link(loc, box(text(font: num-font, size: size, fill: num-fill,
            weight: weight, number-type: "lining", number-width: "tabular", num))),
          link(loc, text(font: t.sans-font, size: size, weight: weight, fill: ink, title)),
          // 쪽번호는 제목보다 0.5pt 작다 → top-edge 0.8em 차이만큼(0.8×0.5=0.4pt)
          // 어센트가 짧아 그냥 top 정렬하면 베이스라인이 0.4pt 위로 뜬다(실측).
          // 셀 상단 inset으로 정확히 상쇄한다.
          grid.cell(inset: (top: 0.4pt),
            link(loc, text(font: t.body-font, size: size - 0.5pt, fill: ink,
              number-type: "lining", number-width: "tabular", page-no))),
        )
      })
    page(
      header: none,
      numbering: "i",
      footer: context align(center, text(font: t.sans-font, size: 9pt, fill: ink,
        counter(page).display("i"))),
      {
        v(24mm)
        text(font: t.display-font, weight: "semibold", size: 16pt, tracking: 1em,
          fill: ink, toc-title)
        // 표제 아래 정확히 10mm. 룰을 그냥 놓으면 문단 어센트(0.8em)가 얹혀
        // 실측 12.6mm가 되므로 높이 0 블록에 place로 앉힌다.
        v(10mm)
        block(width: 100%, height: 0pt, above: 0pt, below: 0pt,
          place(top + left, line(length: 100%, stroke: 0.4pt + rule-c)))
        v(6mm)

        // 장: 10.5pt Medium, 번호 칼럼 `제N장`, 장과 장 사이 2.5mm
        show outline.entry.where(level: 1): it => context {
          let loc = it.element.location()
          let n = query(heading.where(level: 1).before(loc, inclusive: true)).len()
          let (embedded, rest) = bf-split-num(bf-plain(it.element.body))
          toc-row(loc,
            num: if embedded == none { "제" + str(n) + "장" } else { embedded },
            num-font: t.sans-font, num-fill: accent,
            title: if embedded == none { it.element.body } else { rest },
            page-no: it.page(),
            size: 10.5pt, weight: "medium", above: 6pt + 2.5mm, sticky: true)
        }

        // 절: 10pt Regular, 14mm 추가 들여쓰기, 번호 `N.M`
        show outline.entry.where(level: 2): it => context {
          let loc = it.element.location()
          let ch = query(heading.where(level: 1).before(loc))
          let cn = ch.len()
          let sn = if cn == 0 {
            query(heading.where(level: 2).before(loc, inclusive: true)).len()
          } else {
            query(heading.where(level: 2)
              .after(ch.last().location()).before(loc, inclusive: true)).len()
          }
          let (embedded, rest) = bf-split-num(bf-plain(it.element.body))
          toc-row(loc,
            indent: 14mm,
            num: if embedded == none { str(cn) + "." + str(sn) } else { embedded },
            num-font: t.body-font, num-fill: ink,
            title: if embedded == none { it.element.body } else { rest },
            page-no: it.page(),
            size: 10pt, weight: "regular", above: 6pt)
        }

        outline(title: none, depth: 2, indent: 0pt)
      })
  }
  counter(page).update(1)
  body
}
