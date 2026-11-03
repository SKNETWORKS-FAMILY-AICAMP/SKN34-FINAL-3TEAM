"""수식 텍스트 정리 + M1 입력 형식 (학습·서비스 공용).

AI Hub 71716의 풀이·문제 텍스트는 손글씨를 OCR한 LaTeX라서
`$\\frac{3}{8}$`, `\\begin{array}{r} 34\\\\ 15\\\\ \\hline 19 \\end{array}` 같은 모양이다.
앱에서 학생이 직접 치는 답은 `3/8`, `34-15=19` 같은 평문이므로,
학습 데이터도 같은 평문 쪽으로 옮겨서 두 입력의 차이를 줄인다.
"""

import re

_SYMBOLS = {
    r"\times": "×",
    r"\div": "÷",
    r"\cdot": "·",
    r"\cdots": "…",
    r"\ldots": "…",
    r"\square": "□",
    r"\Box": "□",
    r"\bigcirc": "○",
    r"\circ": "°",
    r"\degree": "°",
    r"\triangle": "△",
    r"\bigstar": "★",
    r"\star": "★",
    r"\bullet": "•",
    r"\blacktriangle": "▲",
    r"\blacksquare": "■",
    r"\rightarrow": "→",
    r"\Rightarrow": "⇒",
    r"\leftarrow": "←",
    r"\lt": "<",
    r"\gt": ">",
    r"\le": "≤",
    r"\leq": "≤",
    r"\ge": "≥",
    r"\geq": "≥",
    r"\neq": "≠",
    r"\ne": "≠",
    r"\sim": "~",
    r"\pm": "±",
    r"\pi": "π",
    r"\angle": "∠",
    r"\%": "%",
}
# 내용만 남기고 감싸는 명령은 버림
_WRAPPERS = [
    "text",
    "mathrm",
    "mathbf",
    "boxed",
    "underline",
    "overline",
    "cancel",
    "bcancel",
    "xcancel",
    "smash",
    "displaystyle",
    "textstyle",
    "operatorname",
]
# 통째로 버리는 명령 (간격·크기)
_DROP = [
    "quad",
    "qquad",
    "big",
    "Big",
    "bigg",
    "Bigg",
    "left",
    "right",
    "displaystyle",
    "hline",
    "cline",
    "phantom",
    "hspace",
    "vspace",
    "limits",
    "nonumber",
]

_BRACE = r"\{((?:[^{}]|\{[^{}]*\})*)\}"  # 한 단계 중첩까지 허용


def latex_to_text(s):
    """LaTeX가 섞인 OCR 텍스트를 사람이 읽는 평문에 가깝게 바꾼다. 완벽한 변환이 목표가 아니다."""
    if not s:
        return ""
    t = str(s)
    t = re.sub(r"<[^>]+>", " ", t)  # 문제 속 HTML 표 태그
    # 세로셈 표: 줄바꿈(\\)을 ' / '로, 칸(&)은 공백으로
    t = re.sub(r"\\begin\{(?:array|matrix|aligned|align\*?|cases)\}(?:\s*\{[lcr| ]*\})?", " ", t)
    t = re.sub(r"\\end\{(?:array|matrix|aligned|align\*?|cases)\}", " ", t)
    t = t.replace("\\\\", " / ").replace("&", " ")
    # \phantom{...} 은 내용까지 버림
    t = re.sub(r"\\phantom" + _BRACE, " ", t)
    # 분수: \frac{a}{b} → a/b, 대분수 2\frac{1}{3} → 2 1/3
    for _ in range(3):
        t = re.sub(r"\\[dc]?frac\s*" + _BRACE + r"\s*" + _BRACE, r" \1/\2 ", t)
    t = re.sub(r"\\sqrt" + _BRACE, r"√(\1)", t)
    # \overset{a}{b}, \underset{a}{b} → b (위·아래 작은 글씨는 받아올림 표시가 많아 버림)
    t = re.sub(r"\\(?:overset|underset|stackrel)" + _BRACE + r"\s*" + _BRACE, r"\2", t)
    for w in _WRAPPERS:
        for _ in range(2):
            t = re.sub(r"\\" + w + r"\s*" + _BRACE, r"\1", t)
    for k in sorted(_SYMBOLS, key=len, reverse=True):
        t = re.sub(re.escape(k) + r"(?![a-zA-Z])", _SYMBOLS[k], t)
    for d in _DROP:
        t = re.sub(r"\\" + d + r"(?![a-zA-Z])", " ", t)
    t = re.sub(r"\\[a-zA-Z]+", " ", t)  # 남은 명령은 버림
    t = t.replace("\\,", " ").replace("\\;", " ").replace("\\ ", " ").replace("\\!", "")
    t = t.replace("$", " ").replace("{", "").replace("}", "").replace("~", " ")
    t = re.sub(r"\s*/\s*(?:/\s*)+", " / ", t)  # 빈 줄 여러 개
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip(" /")


def model_input(question, reference_answer, solution):
    """M1이 읽는 두 덩어리.

    학습(prepare/train)·평가(model)와 서비스 추론이 반드시 같은 형식을 쓴다.
    """
    q = latex_to_text(question)
    a = latex_to_text(reference_answer)
    s = latex_to_text(solution)
    first = f"문제: {q}" + (f" / 정답: {a}" if a else "")
    return first, s
