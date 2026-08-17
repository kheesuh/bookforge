// bookforge base library — shared book primitives for all Typst themes.
// A theme imports this, defines its token dict, and calls `book(...)`.
// Tokens contract (all optional, defaults below):
//   trim: (w, h) mm · margin: (top, bottom, left, right) mm
//   brand, brand-light, ink, muted, paper: colors
//   body-font, sans-font, display-font: str/array
//   body-size, body-leading, heading2-size, heading3-size
#let code-font = ((name: "DejaVu Sans Mono", covers: regex("[A-Za-z0-9]")), "Pretendard")

#let default-tokens = (
  trim: (w: 153mm, h: 225mm),
  margin: (top: 22mm, bottom: 20mm, left: 18mm, right: 16mm),
  brand: rgb("#1a5fb4"),
  brand-light: rgb("#e8f0fa"),
  ink: rgb("#1e2228"),
  muted: rgb("#6b7480"),
  paper: white,
  body-font: ("Pretendard",),
  sans-font: ("Pretendard",),
  display-font: ("Pretendard",),
  body-size: 9.5pt,
  body-leading: 0.85em,
  heading2-size: 14pt,
  heading3-size: 11pt,
)

#let merged(tokens) = {
  let t = default-tokens
  for (k, v) in tokens { t.insert(k, v) }
  t
}

// ---- word-keeping for display text (keep-all workaround) -------------------
// Wrap each space-separated word in a box so Korean titles break per word.
#let keep-words(it) = {
  let parts = if type(it) == str { it.split(" ") } else { (it,) }
  if type(it) == str {
    parts.map(w => box(w)).join([ ])
  } else { it }
}

// ---- 평문 추출 --------------------------------------------------------------
// content(제목 본문 등)에서 렌더 가능한 평문만 뽑는다. 폭 실측·말줄임의 전제.
#let plain-text(c) = {
  if c == none { "" }
  else if type(c) == str { c }
  else if c == [ ] { " " }
  else if type(c) == content {
    if c.has("text") { c.text }
    else if c.has("children") { c.children.map(plain-text).fold("", (a, b) => a + b) }
    else if c.has("body") { plain-text(c.body) }
    else { "" }
  } else { str(c) }
}

// ---- 폭 실측 말줄임 ---------------------------------------------------------
// 자수가 아니라 **실제 렌더 폭**을 기준으로 자른다. measure()로 폭을 재며
// 이분탐색으로 `width`에 들어가는 최대 길이를 찾고 "…"를 붙인다.
// (자수 기준 절단은 한글·라틴·숫자의 자폭 차이 때문에 폭을 보장하지 못한다 —
//  러닝헤드 좌우 텍스트가 한 줄에서 충돌하던 결함의 근본 원인.)
// 호출 위치의 text 스타일(서체·급수·자간)이 실측에 그대로 반영되므로
// `set text(...)` 이후에 부를 것.
#let fit-trunc(s, width) = context {
  let txt = plain-text(s)
  if txt == "" {
    // 빈 문자열 — 아무것도 그리지 않는다
  } else if measure(txt).width <= width {
    txt
  } else {
    let cs = txt.clusters()
    // P(n) = (앞 n자 + "…")가 width 이내 — n에 대해 단조. 최대 n을 이분탐색.
    let lo = 0
    let hi = cs.len()
    while lo < hi {
      let mid = int((lo + hi + 1) / 2)
      if measure(cs.slice(0, mid).join("") + "…").width <= width { lo = mid }
      else { hi = mid - 1 }
    }
    if lo <= 0 { "…" } else { cs.slice(0, lo).join("").trim(at: end) + "…" }
  }
}

// ---- full-bleed helper ------------------------------------------------------
// Draws content covering the whole trim, ignoring page margins.
#let full-bleed(t, body) = {
  place(top + left,
    dx: -t.margin.left, dy: -t.margin.top,
    block(width: t.trim.w, height: t.trim.h, body))
}

// ---- chapter opener (dobira) -----------------------------------------------
// Registers a level-1 heading (for outline/bookmarks/running head) and renders
// a full opener page. Theme can override via `opener` callback token.
#let chapter-state = state("bf-chapter", (num: 0, title: ""))

#let chapter(title, summary: none, t: (:), opener: none) = {
  let t = merged(t)
  pagebreak(weak: true)
  chapter-state.update(s => (num: s.num + 1, title: title))
  counter("bf-tbl-n").update(0)
  context {
    let n = chapter-state.get().num
    page(header: none, footer: none, {
      // invisible but real heading: outline + bookmarks + running-head queries
      hide(block(height: 0pt, heading(level: 1, outlined: true, bookmarked: true, title)))
      v(-1.2em)
      set par(justify: false, first-line-indent: 0em)
      if opener != none { (opener)(n, title, summary, t) }
      else {
        full-bleed(t, block(fill: t.brand, width: 100%, height: 100%, inset: (x: t.margin.left, y: t.margin.top), {
          set text(fill: white, font: t.display-font)
          v(8%)
          // str에는 pad 메서드가 없다(typst 0.14) — 2자리 0채움은 직접 만든다
          text(size: 64pt, weight: "black", if n < 10 { "0" + str(n) } else { str(n) })
          v(2em)
          text(size: 24pt, weight: "bold", keep-words(title))
          if summary != none {
            v(2em)
            set text(size: 10.5pt, weight: "regular", fill: white.transparentize(15%))
            set par(leading: 0.9em)
            block(width: 78%, summary)
          }
        }))
      }
    })
  }
}

// pad helper for ints rendered as "01"
#let numpad(n) = if n < 10 { "0" + str(n) } else { str(n) }

// ---- callout boxes ----------------------------------------------------------
// kinds: info / tip / warn / quote / stat  — themes may restyle via show rules
// 문법: 상하 계선 + 라벨 행. 옅은 배경 + 좌측 세로바(박스형 콜아웃)는 쓰지 않는다
// — 단행본 관행이 아니고 생성물 티가 나는 패턴이라 전권에서 제거했다.
// 종류 구분은 색면이 아니라 **라벨 문자열과 라벨 색**이 진다.
#let callout(kind: "info", title: none, t: (:), body) = {
  let t = merged(t)
  let lc = if kind == "warn" { rgb("#c0392b") } else { t.brand }
  let label = if title != none { title }
    else if kind == "warn" { "유의" }
    else if kind == "tip" { "요령" }
    else if kind == "quote" { none }
    else { "정리" }
  block(
    width: 100%, breakable: false, above: 1.2em, below: 1.2em,
    // B4(주의/경고)는 상단 계선을 1.2pt로 굵혀 위계를 준다 — book-anatomy §10
    stroke: (top: (if kind == "warn" { 1.2pt } else { 0.6pt }) + t.ink,
             bottom: 0.3pt + t.ink),
    inset: (x: 0pt, top: 7pt, bottom: 8pt),
    {
      // 박스 내부는 본문 격자(문단 간 1행 공백)를 따르지 않는다 — 밀착 리듬
      set par(spacing: 0.8em, first-line-indent: 0em)
      if label != none {
        text(font: t.sans-font, weight: "semibold", size: 8.5pt,
          tracking: 0.04em, fill: lc, label)
        v(3.5pt)
      }
      set text(size: 0.95em)
      body
    })
}

// big-number stat callout
#let stat(value, label, t: (:)) = {
  let t = merged(t)
  block(breakable: false, {
    text(font: t.display-font, weight: "extrabold", size: 30pt, fill: t.brand, value)
    h(8pt)
    box(baseline: 20%, text(font: t.sans-font, size: 9pt, fill: t.muted, label))
  })
}

// ---- figures ----------------------------------------------------------------
#let bookfig(path, caption: none, source: none, width: 100%, t: (:)) = {
  let t = merged(t)
  // placement: auto — 본문에서 가까운 상/하단으로 부동. bottom 고정은 도해가
  // 단독면으로 떨어질 때 상단 마진 아래가 통째로 비는 구멍을 만든다(시각 판정 C).
  // 인라인 배치는 도해 이월로 앞 면이 반백(G7-MID)이라 부동 자체는 유지.
  figure(
    placement: auto,
    image(path, width: width),
    caption: if caption != none {
      // 캡션·표·그림 규약: 그림 번호 없음, "▲ " + Light 7.5pt, 출처는 다음 줄 "출처 : <이름>"
      text(font: t.sans-font, size: 7.5pt, weight: "light", fill: t.ink, {
        [▲ ]
        caption
        if source != none {
          linebreak()
          text(size: 7pt, fill: t.muted)[출처 : #source]
        }
      })
    } else { none },
    numbering: none,
  )
}

// ---- tables (caption은 콘텐츠가 준다 — 필러 라벨 금지) ----------------------
#let tbl-counter = counter("bf-tbl-n")

#let bf-tbl-base(caption: none, source: none, t: (:), label-fmt: none, body) = {
  let t = merged(t)
  // 표는 분할 가능 — 통짜 표가 남은 공간보다 크면 통째로 이월해 백면·구멍을 만든다.
  // 머리 행 반복은 md2typ가 감싼 table.header가 담당한다.
  block(breakable: true, above: 1.3em, below: 1.3em, width: 100%, {
    if caption != none {
      context {
        tbl-counter.step()
        let n = chapter-state.get().num
        let m = tbl-counter.get().first() + 1
        let lab = if label-fmt != none { (label-fmt)(n, m) } else { "표 " + str(n) + "-" + str(m) }
        text(font: t.sans-font, size: 8.5pt, weight: "semibold", fill: t.brand, lab)
        h(0.6em)
        text(font: t.sans-font, size: 8.5pt, fill: t.ink, caption)
      }
      v(2mm)
    }
    body
    if source != none {
      v(1.5mm)
      text(font: t.sans-font, size: 7.5pt, fill: t.muted, [자료: #source])
    }
  })
}

// ---- front matter -----------------------------------------------------------
#let title-page(meta, t) = {
  page(header: none, footer: none, {
    set par(justify: false, first-line-indent: 0em)
    v(28%)
    set text(font: t.display-font)
    text(size: 26pt, weight: "bold", fill: t.ink, keep-words(meta.title))
    if "subtitle" in meta and meta.subtitle != none {
      v(1.2em)
      text(size: 12pt, fill: t.muted, keep-words(meta.subtitle))
    }
    v(1fr)
    set text(size: 9pt, fill: t.muted)
    if "author" in meta [#meta.author\ ]
    if "date" in meta [#meta.date]
    v(6%)
  })
}

#let colophon(meta, t) = {
  pagebreak(weak: true)
  page(header: none, footer: none, {  // 판권면: 러닝헤드·쪽번호 생략(러닝 시스템 규약)
    set text(size: 8pt, fill: t.muted)
    set par(first-line-indent: 0em)
    v(1fr)
    line(length: 30%, stroke: 0.5pt + t.muted)
    v(6pt)
    text(size: 9.5pt, fill: t.ink, weight: "semibold", meta.title)
    // 부제는 별행 — 제목·부제를 엠대시로 잇는 표기는 쓰지 않는다
    if "subtitle" in meta and meta.subtitle != none { linebreak(); meta.subtitle }
    linebreak()
    if "author" in meta [지은이 #meta.author]
    linebreak()
    if "date" in meta [초판 1쇄 발행 #meta.date]
    linebreak()
    [펴낸곳 bookforge · 조판 bookforge 자동 조판 파이프라인]
    linebreak()
    [본문 서체 #merged((:)).body-font.at(0) · 표제 서체 #merged((:)).display-font.at(0)]
    linebreak()
    [이 책의 내용은 조사 시점 기준이며, 인용·수치는 본문 표기 출처를 따릅니다.]
  })
}

// ---- table of contents ------------------------------------------------------
#let book-toc(t, depth: 2, title: "차례", cols: 1) = {
  page(header: none, footer: none, {
    text(font: t.display-font, size: 20pt, weight: "bold", fill: t.ink, title)
    v(1.8em)
    set text(size: 9.2pt)
    show outline.entry.where(level: 1): it => {
      v(0.9em, weak: true)
      strong(text(font: t.sans-font, size: 10pt, fill: t.brand, it))
    }
    show outline.entry.where(level: 2): it => {
      v(0.45em, weak: true)
      text(size: 8.8pt, it)
    }
    if cols > 1 {
      columns(cols, gutter: 8mm, outline(title: none, depth: depth))
    } else {
      outline(title: none, depth: depth)
    }
  })
}

// ---- master wrapper ---------------------------------------------------------
// theme.typ calls: #show: book.with(meta: (...), tokens: theme-tokens, cover: ..)
#let book(meta: (:), tokens: (:), cover: none, toc: true, toc-title: "차례", toc-cols: 1, body) = {
  let t = merged(tokens)

  set document(title: meta.at("title", default: "무제"), author: meta.at("author", default: "bookforge"))
  set page(
    width: t.trim.w, height: t.trim.h,
    margin: (top: t.margin.top, bottom: t.margin.bottom, left: t.margin.left, right: t.margin.right),
    fill: t.paper,
    footer: context {
      let pn = counter(page).get().first()
      align(center, text(font: t.sans-font, size: 8pt, fill: t.muted, str(pn)))
    },
    header: context {
      let sel = heading.where(level: 1)
      let prev = query(sel.before(here()))
      if prev.len() > 0 {
        // 좌(장 제목) · 우(책 제목)를 **고정 폭 칼럼**으로 나눈다. 가변 길이 텍스트
        // 둘이 한 줄에서 만나 겹치거나 2행으로 흘러넘치던 구조를 제거한 것 —
        // 각 칼럼은 fit-trunc가 실측 폭 기준으로 말줄임하므로 충돌이 불가능하다.
        set text(font: t.sans-font, size: 7.5pt, fill: t.muted, tracking: 0.06em)
        set par(first-line-indent: 0em, justify: false, leading: 0.5em)
        let fw = t.trim.w - t.margin.left - t.margin.right
        let lw = fw * 0.58
        let rw = fw * 0.38
        grid(columns: (lw, 1fr, rw), rows: (auto,),
          fit-trunc(prev.last().body, lw - 2pt),
          [],
          align(right, text(fill: t.brand,
            fit-trunc(meta.at("title", default: ""), rw - 2pt))))
      }
    },
  )
  set text(font: t.body-font, size: t.body-size, fill: t.ink, lang: "ko", region: "KR")
  // 고아/과부 2행 계약(pagination.md §3) — 기본값과 같아도 명시로 고정
  set text(costs: (orphan: 100%, widow: 100%, runt: 200%))
  set par(justify: true, leading: t.body-leading, spacing: 1.15em, first-line-indent: (amount: 1em, all: false))

  // headings 2/3 (level 1 is consumed by chapter())
  show heading.where(level: 2): it => {
    v(1.6em, weak: true)
    block(sticky: true, text(font: t.sans-font, size: t.heading2-size, weight: "bold", fill: t.ink, it.body))
    v(1.0em, weak: true)  // 제목-본문 밀착 방지: 아래 여백은 최소 1행분 확보
  }
  show heading.where(level: 3): it => {
    v(1.2em, weak: true)
    block(sticky: true, {
      box(baseline: -0.12em, circle(radius: 2.2pt, fill: t.brand))
      h(6pt)
      text(font: t.sans-font, size: t.heading3-size, weight: "semibold", fill: t.ink, it.body)
    })
    v(0.75em, weak: true)  // 제목-본문 밀착 방지
  }
  set heading(numbering: none)

  // quotes / lists / code / tables
  // 인용: 좌측 세로바 없이 좌우 들여쓰기만으로 구분한다(단행본 관행).
  show quote.where(block: true): it => block(
    inset: (left: 2em, right: 1em), above: 1em, below: 1em,
    {
      set text(size: 0.95em, fill: t.ink.transparentize(15%))
      set par(first-line-indent: 0em)
      it.body
    })
  set list(marker: ([•], [–]), indent: 0.5em)
  set enum(indent: 0.5em)
  show raw.where(block: true): it => block(
    width: 100%, fill: luma(247), radius: 4pt, inset: 9pt, breakable: true,
    text(font: code-font, size: 8pt, it))
  show raw.where(block: false): it => box(fill: luma(243), radius: 2pt, inset: (x: 3pt, y: 1pt), text(font: code-font, size: 0.92em, it))
  set table(stroke: none, inset: (x: 7pt, y: 6pt))
  show table: it => {
    set text(size: 8.7pt, font: t.sans-font)
    it
  }
  show table.cell.where(y: 0): it => text(weight: "semibold", fill: white, it)
  set table(fill: (x, y) => if y == 0 { t.brand } else if calc.odd(y) { t.brand-light.transparentize(45%) } else { none })
  show figure.where(kind: table): set figure.caption(position: top)
  show figure.caption: it => text(font: t.sans-font, size: 8.5pt, fill: t.muted, it)
  show link: it => text(fill: t.brand, it)

  // front matter
  if cover != none { cover }
  title-page(meta, t)
  if toc { book-toc(t, title: toc-title, cols: toc-cols) }
  counter(page).update(1)

  body
}
