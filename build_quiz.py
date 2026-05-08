from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader


PDF_GLOB_ROOT = Path("E:/")
OUTPUT_HTML = Path("전문간호사_문제풀이.html")

CIRCLED = {
    1: "\u2460",
    2: "\u2461",
    3: "\u2462",
    4: "\u2463",
    5: "\u2464",
}

CHAPTERS = [
    {"id": 1, "part": "PART I", "partTitle": "공통영역", "title": "전문간호사의 역할 및 정책", "qPages": (8, 30), "aPages": (306, 310), "count": 100},
    {"id": 2, "part": "PART I", "partTitle": "공통영역", "title": "병태생리", "qPages": (31, 52), "aPages": (311, 318), "count": 100},
    {"id": 3, "part": "PART I", "partTitle": "공통영역", "title": "약리", "qPages": (53, 74), "aPages": (319, 323), "count": 100},
    {"id": 4, "part": "PART I", "partTitle": "공통영역", "title": "계통별 신체검진법", "qPages": (75, 98), "aPages": (324, 328), "count": 100},
    {"id": 5, "part": "PART II", "partTitle": "전문실무영역", "title": "순환기계", "qPages": (100, 162), "aPages": (329, 340), "count": 200},
    {"id": 6, "part": "PART II", "partTitle": "전문실무영역", "title": "호흡기계", "qPages": (163, 208), "aPages": (341, 352), "count": 200},
    {"id": 7, "part": "PART II", "partTitle": "전문실무영역", "title": "신경계", "qPages": (209, 254), "aPages": (353, 363), "count": 200},
    {"id": 8, "part": "PART II", "partTitle": "전문실무영역", "title": "근골격계", "qPages": (255, 268), "aPages": (364, 366), "count": 54},
    {"id": 9, "part": "PART II", "partTitle": "전문실무영역", "title": "소화기계", "qPages": (269, 276), "aPages": (367, 368), "count": 33},
    {"id": 10, "part": "PART II", "partTitle": "전문실무영역", "title": "내분비계", "qPages": (277, 286), "aPages": (369, 371), "count": 37},
    {"id": 11, "part": "PART II", "partTitle": "전문실무영역", "title": "기타", "qPages": (287, 304), "aPages": (372, 379), "count": 76},
]

CHAPTER_TITLE_NOISE = {
    "전문간호사의 역할 및 정책",
    "병태생리",
    "약리",
    "갹리",
    "계통별 신체검진법",
    "순환기계",
    "호흡기계",
    "호吝기계",
    "호홉기계",
    "호몹기계",
    "신경계",
    "근골격계",
    "소화기계",
    "내분비계",
    "기타",
}


def find_pdf() -> Path:
    candidates = [
        p
        for p in PDF_GLOB_ROOT.glob("*.pdf")
        if not p.name.startswith("._") and p.stat().st_size > 1_000_000
    ]
    if not candidates:
        raise FileNotFoundError("E:/ 드라이브에서 문제집 PDF를 찾지 못했습니다.")
    return max(candidates, key=lambda p: p.stat().st_size)


def compact(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = text.replace("（", "(").replace("）", ")")
    return text.strip()


def page_lines(reader: PdfReader, page_no: int) -> list[str]:
    text = reader.pages[page_no - 1].extract_text() or ""
    return [compact(line) for line in text.splitlines()]


def is_noise(line: str) -> bool:
    if not line:
        return True
    if line in CHAPTER_TITLE_NOISE:
        return True
    if line.startswith("전문간호사 자격시험 대비"):
        return True
    if re.match(r"^(CHAPTER|Chapter|chapter|아iapter|PART|parth)\b", line):
        return True
    if re.search(r"\|\s*\d+\s*$", line) and re.search(r"(PART|part|Chapter|chapter|정답)", line):
        return True
    if re.match(r"^정답\s*및\s*해설", line) or line.startswith("정답및해설"):
        return True
    if line in {"祖止", "施", "決", "III 전문간호사의 역할 및 정책", "PARTI-I"}:
        return True
    return False


def match_question_start(line: str, expected: int) -> re.Match[str] | None:
    match = re.match(r"^\s*0*(\d{1,3})\s+(.+)$", line)
    if not match:
        return None
    number = int(match.group(1))
    if number != expected:
        return None
    return match


def match_choice(line: str) -> tuple[int, str] | None:
    circled = "\u2460\u2461\u2462\u2463\u2464"
    match = re.match(rf"^\s*[\.\-•]?\s*([{circled}])\s*(.*)$", line)
    if match:
        return circled.index(match.group(1)) + 1, match.group(2).strip()

    match = re.match(r"^\s*[®]\s*(.*)$", line)
    if match:
        return 3, match.group(1).strip()

    match = re.match(r"^\s*[@©]\s*(.*)$", line)
    if match:
        return 4, match.group(1).strip()

    match = re.match(r"^\s*[\(\[]\s*([1-5])\s*[\)\]]?\s*(.*)$", line)
    if match:
        return int(match.group(1)), match.group(2).strip()

    return None


def has_all_choices(question: dict | None) -> bool:
    if not question:
        return False
    return all(question["choices"].get(i) for i in range(1, 6))


def finalize_question(question: dict | None, questions: list[dict]) -> None:
    if not question:
        return
    choices = [question["choices"].get(i, "").strip() for i in range(1, 6)]
    question["choices"] = choices
    question["stem"] = "\n".join(question["stem"]).strip()
    if question.get("passage"):
        question["passage"] = "\n".join(question["passage"]).strip()
    else:
        question.pop("passage", None)
    questions.append(question)


def parse_passage_range(line: str) -> tuple[int, int] | None:
    match = re.search(r"문제\s*(\d{1,3})\s*[-~〜]\s*(\d{1,3})", line)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_questions(reader: PdfReader, chapter: dict) -> list[dict]:
    questions: list[dict] = []
    next_number = 1
    current: dict | None = None
    current_choice: int | None = None
    pending_passage: dict | None = None
    collecting_passage = False
    leading_unnumbered_until = 3 if chapter["id"] == 3 else 0

    def start_question(number: int, text: str, page_no: int) -> dict:
        passage_lines = None
        nonlocal pending_passage
        if pending_passage and pending_passage["start"] <= number <= pending_passage["end"]:
            passage_lines = list(pending_passage["lines"])
        if pending_passage and number > pending_passage["end"]:
            pending_passage = None
        question = {
            "id": f"c{chapter['id']:02d}-q{number:03d}",
            "chapterId": chapter["id"],
            "number": number,
            "page": page_no,
            "stem": [text.strip()] if text.strip() else [],
            "choices": {},
        }
        if passage_lines:
            question["passage"] = passage_lines
        return question

    for page_no in range(chapter["qPages"][0], chapter["qPages"][1] + 1):
        for raw_line in page_lines(reader, page_no):
            line = compact(raw_line)
            if is_noise(line):
                continue

            passage_range = parse_passage_range(line)
            if passage_range:
                if current and has_all_choices(current):
                    finalize_question(current, questions)
                    current = None
                    current_choice = None
                pending_passage = {"start": passage_range[0], "end": passage_range[1], "lines": [line]}
                collecting_passage = True
                continue

            q_start = match_question_start(line, next_number)
            if q_start and (current is None or has_all_choices(current)):
                if current:
                    finalize_question(current, questions)
                collecting_passage = False
                current = start_question(next_number, q_start.group(2), page_no)
                next_number += 1
                current_choice = None
                continue

            if collecting_passage and pending_passage:
                pending_passage["lines"].append(line)
                continue

            if current is None and next_number <= leading_unnumbered_until:
                current = start_question(next_number, line, page_no)
                next_number += 1
                current_choice = None
                continue

            if (
                current
                and next_number <= leading_unnumbered_until
                and has_all_choices(current)
                and not match_choice(line)
            ):
                finalize_question(current, questions)
                current = start_question(next_number, line, page_no)
                next_number += 1
                current_choice = None
                continue

            if current is None:
                continue

            choice = match_choice(line)
            if current and has_all_choices(current) and choice and choice[0] == 1:
                finalize_question(current, questions)
                current = start_question(
                    next_number,
                    f"그림/자료 문항입니다. 원문 PDF p.{page_no}를 함께 확인하세요.",
                    page_no,
                )
                next_number += 1
                current_choice, choice_text = choice
                current["choices"][current_choice] = choice_text
                continue

            if choice:
                current_choice, choice_text = choice
                current["choices"][current_choice] = choice_text
                continue

            if current_choice:
                current["choices"][current_choice] = (
                    current["choices"].get(current_choice, "") + " " + line
                ).strip()
            else:
                current["stem"].append(line)

    if current:
        finalize_question(current, questions)

    return questions


def normalize_answer_token(token: str) -> int | None:
    token = token.strip()
    circled = "\u2460\u2461\u2462\u2463\u2464"
    for idx, char in enumerate(circled, start=1):
        if token.startswith(char):
            return idx
    parenthesized = re.match(r"^[\(\[]\s*([1-5S])\s*[\)\]]?", token, re.I)
    if parenthesized:
        value = parenthesized.group(1).upper()
        return 5 if value == "S" else int(value)
    if token.startswith("@") or token.startswith("®") or token.startswith("©"):
        return 4
    return None


MANUAL_ANSWERS = {
    (11, 73): {
        "answer": 2,
        "answerLabel": CIRCLED[2],
        "answerPage": 376,
        "explanation": "성인의 9의 법칙에서 한쪽 하지 전체는 18%이며, 앞 표면은 약 9%로 계산한다.",
    }
}


def match_answer_start(line: str, expected: int, max_number: int) -> tuple[int, int, str] | None:
    match = re.match(r"^\s*(\d{1,3})\s*[\.\u2022．]?\s*(\S{1,6})\s*(.*)$", line)
    if not match:
        return None
    number = int(match.group(1))
    if number != expected and not (expected < number <= max_number):
        return None
    answer = normalize_answer_token(match.group(2))
    if answer is None:
        return None
    return number, answer, match.group(3).strip()


def finalize_answer(answer: dict | None, answers: dict[int, dict]) -> None:
    if not answer:
        return
    answer["explanation"] = "\n".join(answer["lines"]).strip()
    answer.pop("lines", None)
    answers[answer["number"]] = answer


def parse_answers(reader: PdfReader, chapter: dict) -> dict[int, dict]:
    answers: dict[int, dict] = {}
    expected = 1
    current: dict | None = None

    for page_no in range(chapter["aPages"][0], chapter["aPages"][1] + 1):
        for raw_line in page_lines(reader, page_no):
            line = compact(raw_line)
            if is_noise(line):
                continue

            start = match_answer_start(line, expected, chapter["count"])
            if start:
                finalize_answer(current, answers)
                number, answer_index, rest = start
                current = {
                    "number": number,
                    "answer": answer_index,
                    "answerLabel": CIRCLED[answer_index],
                    "answerPage": page_no,
                    "lines": [rest] if rest else [],
                }
                expected = number + 1
                continue

            if current:
                current["lines"].append(line)

    finalize_answer(current, answers)
    return answers


def build_data(pdf_path: Path) -> dict:
    reader = PdfReader(str(pdf_path))
    chapters = []
    diagnostics = []

    for chapter in CHAPTERS:
        questions = parse_questions(reader, chapter)
        answers = parse_answers(reader, chapter)
        for (chapter_id, number), answer in MANUAL_ANSWERS.items():
            if chapter_id == chapter["id"]:
                answers[number] = {"number": number, **answer}
        for question in questions:
            answer = answers.get(question["number"])
            if answer:
                question.update(answer)
            else:
                question["answer"] = None
                question["answerLabel"] = ""
                question["explanation"] = ""

        diagnostics.append(
            {
                "chapter": chapter["id"],
                "title": chapter["title"],
                "questions": len(questions),
                "answers": len(answers),
                "expected": chapter["count"],
                "missingQuestionAnswers": [
                    q["number"] for q in questions if q.get("answer") is None
                ],
                "choiceIssues": [
                    q["number"] for q in questions if len(q["choices"]) != 5 or any(not c for c in q["choices"])
                ],
            }
        )

        chapters.append(
            {
                "id": chapter["id"],
                "part": chapter["part"],
                "partTitle": chapter["partTitle"],
                "title": chapter["title"],
                "count": chapter["count"],
                "startPage": chapter["qPages"][0],
                "endPage": chapter["qPages"][1],
                "questions": questions,
            }
        )

    return {
        "source": pdf_path.name,
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "totalQuestions": sum(len(ch["questions"]) for ch in chapters),
        "chapters": chapters,
        "diagnostics": diagnostics,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>전문간호사 자격시험 문제풀이</title>
  <style>
    :root {
      --ink: #181611;
      --muted: #6f695f;
      --line: #d8d0c2;
      --paper: #fffdf8;
      --warm: #f3efe7;
      --accent: #4e1f18;
      --accent-2: #8f4d2d;
      --ok: #1f6f43;
      --bad: #a6342b;
      --shadow: 0 18px 40px rgba(42, 33, 23, 0.14);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(78,31,24,.06) 0 1px, transparent 1px 100%),
        linear-gradient(#eee8db, #faf7ef 34%, #efe8da);
      font-family: "Noto Serif KR", "Batang", "Apple SD Gothic Neo", "Malgun Gothic", serif;
    }
    button, input, select {
      font: inherit;
    }
    .app {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      min-height: 100vh;
    }
    aside {
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 24px 18px;
      background: #f8f3e9;
      border-right: 1px solid var(--line);
      overflow: auto;
    }
    .brand {
      padding: 4px 4px 18px;
      border-bottom: 2px solid var(--accent);
      margin-bottom: 18px;
    }
    .brand small {
      display: block;
      color: var(--accent-2);
      font-size: 12px;
      letter-spacing: .08em;
      font-weight: 700;
    }
    .brand h1 {
      margin: 6px 0 0;
      line-height: 1.15;
      font-size: 24px;
      font-weight: 800;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 16px;
    }
    .stat {
      padding: 10px 8px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 6px;
      text-align: center;
    }
    .stat b { display: block; font-size: 20px; }
    .stat span { color: var(--muted); font-size: 12px; }
    .search {
      width: 100%;
      height: 42px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--paper);
      color: var(--ink);
    }
    .filters {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      margin: 10px 0 16px;
    }
    .chip {
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--paper);
      color: var(--muted);
      cursor: pointer;
    }
    .chip.active {
      border-color: var(--accent);
      background: var(--accent);
      color: #fffaf0;
    }
    .chapters {
      display: grid;
      gap: 8px;
    }
    .chapter {
      width: 100%;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--paper);
      text-align: left;
      cursor: pointer;
    }
    .chapter.active {
      border-color: var(--accent);
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .chapter strong {
      display: block;
      font-size: 14px;
      line-height: 1.35;
    }
    .chapter span {
      display: block;
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    main {
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 0;
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 3;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 28px;
      background: rgba(250, 247, 239, .88);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(12px);
    }
    .selects {
      display: flex;
      gap: 8px;
      min-width: 0;
    }
    select {
      min-width: 130px;
      height: 38px;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--paper);
      color: var(--ink);
    }
    .nav {
      display: flex;
      gap: 8px;
    }
    .iconbtn {
      width: 42px;
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--paper);
      color: var(--ink);
      cursor: pointer;
    }
    .stage {
      display: grid;
      place-items: start center;
      padding: 32px 28px 44px;
    }
    .page {
      width: min(920px, 100%);
      min-height: 760px;
      padding: 42px 52px 28px;
      background: var(--paper);
      border: 1px solid #e7dfd2;
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .page-head {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      border-bottom: 2px solid var(--ink);
      padding-bottom: 12px;
      margin-bottom: 22px;
    }
    .chapter-title {
      min-width: 0;
    }
    .chapter-title small {
      display: block;
      color: var(--accent-2);
      font-size: 13px;
      font-weight: 700;
    }
    .chapter-title h2 {
      margin: 4px 0 0;
      font-size: clamp(22px, 3vw, 34px);
      line-height: 1.15;
      letter-spacing: 0;
    }
    .page-no {
      flex: 0 0 auto;
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }
    .passage {
      margin: 0 0 22px;
      padding: 18px 20px;
      border-left: 4px solid var(--accent);
      background: var(--warm);
      white-space: pre-line;
      line-height: 1.75;
    }
    .question-line {
      display: grid;
      grid-template-columns: 58px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      margin-bottom: 22px;
    }
    .qnum {
      color: var(--accent);
      font-size: 28px;
      font-weight: 800;
      line-height: 1;
    }
    .stem {
      white-space: pre-line;
      font-size: 20px;
      line-height: 1.75;
      word-break: keep-all;
      overflow-wrap: anywhere;
    }
    .options {
      display: grid;
      gap: 10px;
      margin-left: 70px;
    }
    .option {
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr);
      gap: 10px;
      align-items: start;
      min-height: 48px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fffefa;
      color: var(--ink);
      text-align: left;
      cursor: pointer;
      line-height: 1.6;
    }
    .option:hover { border-color: #b79d86; }
    .option .mark {
      color: var(--accent);
      font-weight: 800;
    }
    .option.correct {
      border-color: rgba(31,111,67,.55);
      background: #eef8f1;
    }
    .option.wrong {
      border-color: rgba(166,52,43,.55);
      background: #fff0ee;
    }
    .answer {
      display: none;
      margin: 24px 0 0 70px;
      padding: 18px 20px;
      border-top: 2px solid var(--accent);
      background: var(--warm);
      line-height: 1.75;
      white-space: pre-line;
    }
    .answer.show { display: block; }
    .answer b {
      display: block;
      color: var(--accent);
      margin-bottom: 8px;
      font-size: 18px;
    }
    .page-foot {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 34px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
    }
    .bookmark {
      border: 0;
      background: transparent;
      color: var(--accent);
      cursor: pointer;
      font-size: 18px;
    }
    .empty {
      width: min(720px, 100%);
      margin: 80px auto;
      padding: 34px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      text-align: center;
    }
    @media (max-width: 900px) {
      .app { grid-template-columns: 1fr; }
      aside {
        position: static;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .chapters {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .topbar {
        position: static;
        padding: 14px 16px;
        flex-wrap: wrap;
      }
      .stage { padding: 18px 12px 32px; }
      .page {
        min-height: 0;
        padding: 26px 18px 20px;
      }
      .question-line {
        grid-template-columns: 1fr;
        gap: 8px;
      }
      .qnum { font-size: 22px; }
      .stem { font-size: 17px; }
      .options, .answer { margin-left: 0; }
      .selects {
        width: 100%;
        display: grid;
        grid-template-columns: 1fr 1fr;
      }
      select { min-width: 0; width: 100%; }
    }
    @media (max-width: 560px) {
      .chapters { grid-template-columns: 1fr; }
      .filters { grid-template-columns: repeat(2, 1fr); }
      .page-head { display: block; }
      .page-no { margin-top: 10px; text-align: left; }
      .option { grid-template-columns: 28px minmax(0, 1fr); }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand">
        <small>Practice Nurse</small>
        <h1>전문간호사<br>자격시험 대비</h1>
      </div>
      <div class="stats">
        <div class="stat"><b id="doneCount">0</b><span>풀이</span></div>
        <div class="stat"><b id="rightCount">0</b><span>정답</span></div>
        <div class="stat"><b id="rateCount">0%</b><span>정답률</span></div>
      </div>
      <input class="search" id="search" type="search" placeholder="검색">
      <div class="filters">
        <button class="chip active" data-filter="all">전체</button>
        <button class="chip" data-filter="unsolved">미풀이</button>
        <button class="chip" data-filter="wrong">오답</button>
        <button class="chip" data-filter="bookmarked">표시</button>
      </div>
      <div class="chapters" id="chapters"></div>
    </aside>
    <main>
      <div class="topbar">
        <div class="selects">
          <select id="chapterSelect"></select>
          <select id="questionSelect"></select>
        </div>
        <div class="nav">
          <button class="iconbtn" id="prev" title="이전">‹</button>
          <button class="iconbtn" id="shuffle" title="무작위">↯</button>
          <button class="iconbtn" id="next" title="다음">›</button>
        </div>
      </div>
      <section class="stage" id="stage"></section>
    </main>
  </div>
  <script>
    const QUIZ_DATA = __DATA__;
    const marks = ["①", "②", "③", "④", "⑤"];
    const storageKey = "np_quiz_progress_v1";
    const progress = JSON.parse(localStorage.getItem(storageKey) || "{}");
    let state = { chapterId: QUIZ_DATA.chapters[0].id, index: 0, filter: "all", query: "" };

    const $ = (selector) => document.querySelector(selector);
    const chaptersEl = $("#chapters");
    const stage = $("#stage");
    const chapterSelect = $("#chapterSelect");
    const questionSelect = $("#questionSelect");

    function save() {
      localStorage.setItem(storageKey, JSON.stringify(progress));
      renderStats();
      renderChapters();
    }

    function chapter() {
      return QUIZ_DATA.chapters.find((item) => item.id === state.chapterId);
    }

    function allQuestions() {
      return QUIZ_DATA.chapters.flatMap((ch) => ch.questions.map((q) => ({...q, chapter: ch})));
    }

    function questionList() {
      const query = state.query.trim().toLowerCase();
      return chapter().questions.filter((q) => {
        const item = progress[q.id] || {};
        const solved = Number.isInteger(item.choice);
        const isWrong = solved && item.choice !== q.answer;
        const isBookmarked = item.bookmarked;
        if (state.filter === "unsolved" && solved) return false;
        if (state.filter === "wrong" && !isWrong) return false;
        if (state.filter === "bookmarked" && !isBookmarked) return false;
        if (!query) return true;
        const haystack = [q.stem, q.passage || "", q.explanation || "", ...(q.choices || [])].join(" ").toLowerCase();
        return haystack.includes(query);
      });
    }

    function currentQuestion() {
      const list = questionList();
      if (!list.length) return null;
      state.index = Math.max(0, Math.min(state.index, list.length - 1));
      return list[state.index];
    }

    function renderStats() {
      const solved = allQuestions().filter(({id}) => Number.isInteger((progress[id] || {}).choice));
      const right = solved.filter((q) => (progress[q.id] || {}).choice === q.answer);
      $("#doneCount").textContent = solved.length;
      $("#rightCount").textContent = right.length;
      $("#rateCount").textContent = solved.length ? Math.round(right.length / solved.length * 100) + "%" : "0%";
    }

    function renderChapters() {
      chaptersEl.innerHTML = "";
      QUIZ_DATA.chapters.forEach((ch) => {
        const solved = ch.questions.filter((q) => Number.isInteger((progress[q.id] || {}).choice)).length;
        const btn = document.createElement("button");
        btn.className = "chapter" + (ch.id === state.chapterId ? " active" : "");
        btn.innerHTML = `<strong>Chapter ${String(ch.id).padStart(2, "0")} ${ch.title}</strong><span>${ch.part} ${ch.partTitle} · ${solved}/${ch.questions.length}</span>`;
        btn.addEventListener("click", () => {
          state.chapterId = ch.id;
          state.index = 0;
          renderAll();
        });
        chaptersEl.appendChild(btn);
      });
    }

    function renderSelects() {
      chapterSelect.innerHTML = QUIZ_DATA.chapters.map((ch) => `<option value="${ch.id}">Chapter ${String(ch.id).padStart(2, "0")} ${ch.title}</option>`).join("");
      chapterSelect.value = state.chapterId;
      const list = questionList();
      questionSelect.innerHTML = list.map((q, idx) => `<option value="${idx}">${String(q.number).padStart(2, "0")}번</option>`).join("");
      questionSelect.value = state.index;
    }

    function renderQuestion() {
      const q = currentQuestion();
      if (!q) {
        stage.innerHTML = `<div class="empty">표시할 문항이 없습니다.</div>`;
        return;
      }
      const ch = chapter();
      const item = progress[q.id] || {};
      const chosen = item.choice;
      const answered = Number.isInteger(chosen);
      const answerText = q.answer ? `${marks[q.answer - 1]} ${q.choices[q.answer - 1] || ""}` : "";
      stage.innerHTML = `
        <article class="page">
          <header class="page-head">
            <div class="chapter-title">
              <small>${ch.part} ${ch.partTitle}</small>
              <h2>Chapter ${String(ch.id).padStart(2, "0")} ${ch.title}</h2>
            </div>
            <div class="page-no">문제 p.${q.page}<br>해설 p.${q.answerPage || "-"}</div>
          </header>
          ${q.passage ? `<section class="passage">${escapeHtml(q.passage)}</section>` : ""}
          <div class="question-line">
            <div class="qnum">${String(q.number).padStart(2, "0")}</div>
            <div class="stem">${escapeHtml(q.stem)}</div>
          </div>
          <div class="options">
            ${q.choices.map((choice, idx) => {
              const value = idx + 1;
              let cls = "option";
              if (answered && value === q.answer) cls += " correct";
              if (answered && value === chosen && chosen !== q.answer) cls += " wrong";
              return `<button class="${cls}" data-choice="${value}"><span class="mark">${marks[idx]}</span><span>${escapeHtml(choice)}</span></button>`;
            }).join("")}
          </div>
          <section class="answer ${answered ? "show" : ""}">
            <b>정답 ${escapeHtml(answerText)}</b>
            ${escapeHtml(q.explanation || "")}
          </section>
          <footer class="page-foot">
            <span>${ch.part} ${ch.partTitle} | ${q.page}</span>
            <button class="bookmark" id="bookmark" title="표시">${item.bookmarked ? "★" : "☆"}</button>
          </footer>
        </article>
      `;
      stage.querySelectorAll(".option").forEach((button) => {
        button.addEventListener("click", () => {
          progress[q.id] = {...(progress[q.id] || {}), choice: Number(button.dataset.choice)};
          save();
          renderQuestion();
        });
      });
      $("#bookmark").addEventListener("click", () => {
        progress[q.id] = {...(progress[q.id] || {}), bookmarked: !(progress[q.id] || {}).bookmarked};
        save();
        renderQuestion();
      });
    }

    function escapeHtml(value) {
      return String(value || "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      })[char]);
    }

    function move(delta) {
      const list = questionList();
      if (!list.length) return;
      state.index = (state.index + delta + list.length) % list.length;
      renderAll();
    }

    function renderAll() {
      renderStats();
      renderChapters();
      renderSelects();
      renderQuestion();
    }

    chapterSelect.addEventListener("change", () => {
      state.chapterId = Number(chapterSelect.value);
      state.index = 0;
      renderAll();
    });
    questionSelect.addEventListener("change", () => {
      state.index = Number(questionSelect.value);
      renderAll();
    });
    $("#prev").addEventListener("click", () => move(-1));
    $("#next").addEventListener("click", () => move(1));
    $("#shuffle").addEventListener("click", () => {
      const list = questionList();
      if (!list.length) return;
      state.index = Math.floor(Math.random() * list.length);
      renderAll();
    });
    $("#search").addEventListener("input", (event) => {
      state.query = event.target.value;
      state.index = 0;
      renderAll();
    });
    document.querySelectorAll(".chip").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".chip").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        state.filter = button.dataset.filter;
        state.index = 0;
        renderAll();
      });
    });
    window.addEventListener("keydown", (event) => {
      if (event.target.matches("input, select")) return;
      if (event.key === "ArrowLeft") move(-1);
      if (event.key === "ArrowRight") move(1);
      if (/^[1-5]$/.test(event.key)) {
        const q = currentQuestion();
        if (!q) return;
        progress[q.id] = {...(progress[q.id] || {}), choice: Number(event.key)};
        save();
        renderQuestion();
      }
    });

    renderAll();
  </script>
</body>
</html>
"""


def write_html(data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA__", payload)
    OUTPUT_HTML.write_text(html, encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else find_pdf()
    data = build_data(pdf_path)
    write_html(data)
    print(f"PDF: {pdf_path}")
    print(f"HTML: {OUTPUT_HTML.resolve()}")
    print(f"Total: {data['totalQuestions']}")
    for item in data["diagnostics"]:
        print(
            f"Chapter {item['chapter']:02d}: "
            f"questions={item['questions']}/{item['expected']} "
            f"answers={item['answers']}/{item['expected']} "
            f"missing_answers={item['missingQuestionAnswers'][:10]} "
            f"choice_issues={item['choiceIssues'][:10]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
