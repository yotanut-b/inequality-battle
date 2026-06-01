import json
import re
from pathlib import Path


DOWNLOADS = Path.home() / "Downloads"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "questions"
SOURCES = {
    "addition": [DOWNLOADS / "1. สมบัติการบวก.txt"],
    "multiplication": [DOWNLOADS / "2. สมบัติการคูณ.txt"],
    "linear": [DOWNLOADS / f"3. อสมการ ({level}).txt" for level in range(1, 6)],
}
TITLES = {
    "addition": "การแก้อสมการโดยใช้สมบัติการบวกของการไม่เท่ากัน",
    "multiplication": "การแก้อสมการโดยใช้สมบัติการคูณของการไม่เท่ากัน",
    "linear": "การแก้อสมการเชิงเส้นตัวแปรเดียว",
}


def to_latex(text):
    text = text.replace("≤", r"\leq ").replace("≥", r"\geq ").replace("≠", r"\neq ")
    text = re.sub(r"(?<![\w)])(-?\d+|x)/\((-?\d+)\)", r"\\frac{\1}{(\2)}", text)
    text = re.sub(r"(?<![\w)])(-?\d+|x)/(-?\d+)", r"\\frac{\1}{\2}", text)
    text = re.sub(r"\((-?\d+)/(-?\d+)\)", r"\\left(\\frac{\1}{\2}\\right)", text)
    return text


def parse_questions(path, fixed_level=None):
    text = path.read_text(encoding="utf-8-sig")
    current_level = fixed_level
    questions = []
    lines = [line.strip() for line in text.splitlines()]
    index = 0
    while index < len(lines):
        level_match = re.match(r"LEVEL\s+(\d+)", lines[index], re.IGNORECASE)
        if level_match:
            current_level = int(level_match.group(1))
            index += 1
            continue
        if re.match(r"ข้อ\s+\d+$", lines[index]):
            if current_level is None:
                raise ValueError(f"ไม่พบระดับก่อนโจทย์ใน {path.name}")
            question_text = lines[index + 1]
            choices = []
            for choice_offset in range(2, 6):
                choice_match = re.match(r"\d+\.\s*(.+)", lines[index + choice_offset])
                if not choice_match:
                    raise ValueError(f"ตัวเลือกไม่ครบหลัง {lines[index]} ใน {path.name}")
                value = choice_match.group(1).strip()
                choices.append({"value": value, "latex": to_latex(value)})
            answer_match = re.match(r"Answer:\s*(\d+)", lines[index + 6], re.IGNORECASE)
            if not answer_match:
                raise ValueError(f"ไม่พบ Answer หลัง {lines[index]} ใน {path.name}")
            answer_index = int(answer_match.group(1)) - 1
            questions.append(
                {
                    "level": current_level,
                    "text": question_text,
                    "latex": to_latex(question_text),
                    "answer": choices[answer_index]["value"],
                    "choices": choices,
                }
            )
            index += 7
            continue
        index += 1
    return questions


def build_topic(topic, paths):
    questions = []
    for index, path in enumerate(paths, start=1):
        fixed_level = index if topic == "linear" else None
        questions.extend(parse_questions(path, fixed_level))
    levels = {}
    for question in questions:
        level = str(question.pop("level"))
        levels.setdefault(level, []).append(question)
    return {"title": TITLES[topic], "levels": levels}


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    summary = {}
    for topic, paths in SOURCES.items():
        data = build_topic(topic, paths)
        target = OUTPUT_DIR / f"{topic}.json"
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        summary[topic] = {level: len(items) for level, items in data["levels"].items()}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
