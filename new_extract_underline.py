import json
import re
import fitz
from pathlib import Path

# =========================
# PATTERNS
# =========================

START_SECTION_PATTERN = re.compile(
    r"9\.\s*Details of the Provisional Refusal", re.IGNORECASE
)

MAIN_START_PATTERN = re.compile(
    r"This\s+International\s+Registration\s+is\s+not\s+eligible\s+for\s+registration\s+due\s+to\s+the\s+following",
    re.IGNORECASE
)

GROUND_HEADER_PATTERN = re.compile(
    r"^\s*(?:\(\s*)?Ground\s*(\d+)?\s*(?:\)|\.)?\s*$",
    re.IGNORECASE
)

GUIDANCE_PATTERN = re.compile(
    r"10\.\s*Guidance", re.IGNORECASE
)

NOTE_PATTERN = re.compile(
    r"(☞\s*Please\s+note\s+that|※\s*Note\s*:?)",
    re.IGNORECASE
)

GOODS_SERVICES_START_PATTERN = re.compile(
    r"^\s*-\s*Goods/services\s*:\s*$",
    re.IGNORECASE
)

GOODS_SERVICES_END_PATTERN = re.compile(
    r"^\s*-\s*Reproduction\s+of\s+the\s+mark\s*:",
    re.IGNORECASE
)

IGNORE_TEXT = "<Indefinite identification (underlined goods/services)>"

EARLIER_MARK_PATTERN = re.compile(
    r"Information\s+concerning\s+the\s+earlier\s+mark(\s*\(?\d*\)?)?",
    re.IGNORECASE
)

FILING_NUMBER_PATTERN = re.compile(
    r"-\s*Filing\s+number\s*:\s*([A-Z0-9\-]+)",
    re.IGNORECASE
)

INTL_REG_NUMBER_PATTERN = re.compile(
    r"-\s*International\s+registration\s+number\s*:\s*([A-Z0-9\-]+)",
    re.IGNORECASE
)

CLASS_PATTERN = re.compile(
    r"\[\s*Class\s*(\d+)\s*\]",
    re.IGNORECASE
)

APPLIED_GOODS_PATTERN = re.compile(
    r"\*\s*Goods/services\s+of\s+the\s+applied-for\s+mark\s+in\s+relation\s+to\s+this\s+ground\s*:",
    re.IGNORECASE
)

INTRO_SKIP_PATTERN = re.compile(
    r"^(The\s+International\s+Registration\s+has\s+been"
    r"|This\s+International\s+Registration\s+is\s+not"
    r"|eligible\s+for\s+registration\s+for\s+the\s+following)",
    re.IGNORECASE
)

TRAILING_PUNCT_PATTERN = re.compile(r"^(.*?)([;,.]*)$")

PUNCT_RE = re.compile(r"^(.*?)([;.,]+)?$")

CLASS_HEADER_RE = re.compile(r"^\[\s*Class\s*\d+\s*\]\s*", re.IGNORECASE)

UNDERLINE_RE = re.compile(r"<u>.*?</u>", re.IGNORECASE)

# =========================
# CORE
# =========================
def extract_ground_ranges(pdf_path: str) -> list[dict]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    doc = fitz.open(pdf_path)
    results = []

    section_started = False
    current_ground = None
    removing = False
    removing_goods_services = False

    for page in doc:
        # 🔥 페이지 단위 exclusion rect 계산
        exclusion_rects = _find_exclusion_rects(page)

        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue

            for line in block["lines"]:
                spans = line["spans"]

                # line 전체가 exclusion rect와 겹치면 skip
                if any(_is_inside_any_rect(s["bbox"], exclusion_rects) for s in spans):
                    continue

                line_text = "".join(s["text"] for s in spans).strip()
                if not line_text:
                    continue

                # ─────────────────────────────
                # 1️⃣ 9번 섹션 시작
                # ─────────────────────────────
                if not section_started:
                    if START_SECTION_PATTERN.search(line_text):
                        section_started = True
                    continue

                # ─────────────────────────────
                # 1️⃣-1️⃣ 안내 문구 스킵
                # ─────────────────────────────
                if INTRO_SKIP_PATTERN.match(line_text):
                    continue

                # ─────────────────────────────
                # 2️⃣ Goods/services 제거
                # ─────────────────────────────
                if GOODS_SERVICES_START_PATTERN.match(line_text):
                    removing_goods_services = True
                    continue

                if removing_goods_services:
                    if GOODS_SERVICES_END_PATTERN.match(line_text):
                        removing_goods_services = False
                    continue

                # ─────────────────────────────
                # 3️⃣ 무시 텍스트
                # ─────────────────────────────
                if IGNORE_TEXT in line_text:
                    continue

                # ─────────────────────────────
                # 4️⃣ 10. Guidance → 종료
                # ─────────────────────────────
                if GUIDANCE_PATTERN.search(line_text):
                    doc.close()
                    return results

                # ─────────────────────────────
                # 5️⃣ Ground 헤더
                # ─────────────────────────────
                m = GROUND_HEADER_PATTERN.match(line_text)
                if m:
                    current_ground = {
                        "ground": line_text,
                        "ground_type": "GROUND",
                        "ground_number": int(m.group(1)) if m.group(1) else None,
                        "blocks": []
                    }
                    results.append(current_ground)
                    removing = False
                    continue

                # ─────────────────────────────
                # 6️⃣ Ground 없는 문서
                # ─────────────────────────────
                if section_started and current_ground is None:
                    current_ground = {
                        "ground": None,
                        "ground_type": "NO_GROUND",
                        "ground_number": None,
                        "blocks": []
                    }
                    results.append(current_ground)

                # ─────────────────────────────
                # 7️⃣ NOTE 제거
                # ─────────────────────────────
                if NOTE_PATTERN.search(line_text):
                    removing = True
                    continue

                if removing and (
                    GROUND_HEADER_PATTERN.match(line_text)
                    or GUIDANCE_PATTERN.search(line_text)
                ):
                    removing = False
                    continue

                # ─────────────────────────────
                # 8️⃣ 본문 수집
                # ─────────────────────────────
                if current_ground and not removing:
                    for s in spans:
                        # 🔥 span 단위 exclusion 재확인
                        if _is_inside_any_rect(s["bbox"], exclusion_rects):
                            continue

                        text = s["text"].strip()
                        if not text:
                            continue

                        current_ground["blocks"].append({
                            "text": text,
                            "bbox": [round(v, 2) for v in s["bbox"]],
                            "page": page.number + 1
                        })

    doc.close()
    return results

def classify_ground_earlier_class(grounds: list[dict]) -> list[dict]:
    final_results = []

    for g in grounds:
        ground_result = {
            "ground": g["ground"],
            "ground_type": g["ground_type"],
            "ground_number": g["ground_number"],
            "earlier_marks": [],
            "classes": [],
            "all_goods_rejected": False
        }

        blocks = g["blocks"]

        inside_earlier = False
        current_earlier = None
        current_class = None

        collecting_applied_goods = False   # 🔥 추가
        applied_goods_blocks = []           # 🔥 추가

        def flush_class():
            nonlocal current_class
            if current_class:
                if inside_earlier and current_earlier:
                    current_earlier["classes"].append(current_class)
                else:
                    ground_result["classes"].append(current_class)
                current_class = None

        def flush_earlier():
            nonlocal current_earlier
            if current_earlier:
                if current_class:
                    current_earlier["classes"].append(current_class)

                # 🔥 Class가 없고 applied goods가 있으면 대체 Class 생성
                if not current_earlier["classes"] and applied_goods_blocks:
                    current_earlier["classes"].append({
                        "class": None,
                        "blocks": applied_goods_blocks.copy()
                    })

                ground_result["earlier_marks"].append(current_earlier)

        for blk in blocks:
            text = blk["text"]

            # ───────── Earlier mark 시작 ─────────
            if EARLIER_MARK_PATTERN.search(text):
                flush_class()
                if current_earlier:
                    flush_earlier()

                inside_earlier = True
                current_earlier = {
                    "filing_number": None,
                    "international_registration_number": None,
                    "classes": []
                }

                collecting_applied_goods = False
                applied_goods_blocks = []
                continue

            # ───────── Filing / International 번호 ─────────
            if inside_earlier:
                m_file = FILING_NUMBER_PATTERN.search(text)
                if m_file:
                    current_earlier["filing_number"] = m_file.group(1)
                    continue

                m_intl = INTL_REG_NUMBER_PATTERN.search(text)
                if m_intl:
                    current_earlier["international_registration_number"] = m_intl.group(1)
                    continue

            # ───────── Applied-for goods 시작 🔥 ─────────
            if inside_earlier and APPLIED_GOODS_PATTERN.search(text):
                collecting_applied_goods = True
                continue

            # ───────── Class 헤더 ─────────
            m_class = CLASS_PATTERN.search(text)
            if m_class:
                collecting_applied_goods = False
                flush_class()
                current_class = {
                    "class": m_class.group(1),
                    "blocks": [blk]
                }
                continue

            # ───────── Applied-for goods 수집 🔥 ─────────
            if collecting_applied_goods:
                applied_goods_blocks.append(blk)
                continue

            # ───────── Class 내부 텍스트 ─────────
            if current_class:
                current_class["blocks"].append(blk)

        flush_class()
        if current_earlier:
            flush_earlier()

        # ✅ Ground 단위 all designated goods
        if not ground_result["earlier_marks"] and not ground_result["classes"]:
            ground_result["earlier_marks"].append({
                "filing_number": None,
                "international_registration_number": None,
                "classes": [{
                    "class": None,
                    "blocks": [{
                        "text": "all designated goods/services",
                        "bbox": [],
                        "page": None
                    }]
                }]
            })

        final_results.append(ground_result)

    return final_results

def extract_underlined_texts(pdf_path: str) -> list[dict]:
    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    results = []

    section_started = False
    content_started = False
    removing_goods_services = False
    removing_note = False

    for page in doc:
        page_no = page.number + 1
        page_dict = page.get_text("dict")

        # ─────────────────────────────
        # 1️⃣ 텍스트 상태 먼저 계산
        # ─────────────────────────────
        text_states = []  # [(y, is_valid)]

        for block in page_dict.get("blocks", []):
            if block["type"] != 0:
                continue

            for line in block["lines"]:
                y = line["bbox"][1]
                text = "".join(span["text"] for span in line["spans"]).strip()
                if not text:
                    continue

                if not section_started:
                    if START_SECTION_PATTERN.search(text):
                        section_started = True
                    text_states.append((y, False))
                    continue

                if section_started and not content_started:
                    if MAIN_START_PATTERN.search(text):
                        content_started = True
                    text_states.append((y, False))
                    continue

                if GOODS_SERVICES_START_PATTERN.match(text):
                    removing_goods_services = True
                    text_states.append((y, False))
                    continue

                if removing_goods_services:
                    if GOODS_SERVICES_END_PATTERN.match(text):
                        removing_goods_services = False
                    text_states.append((y, False))
                    continue

                if NOTE_PATTERN.search(text):
                    removing_note = True
                    text_states.append((y, False))
                    continue

                if removing_note:
                    if GROUND_HEADER_PATTERN.match(text):
                        removing_note = False
                    text_states.append((y, False))
                    continue

                if IGNORE_TEXT in text:
                    text_states.append((y, False))
                    continue

                if GUIDANCE_PATTERN.search(text):
                    doc.close()
                    return results

                text_states.append((y, True))

        # ─────────────────────────────
        # 2️⃣ underline → 텍스트 매핑 + 필터
        # ─────────────────────────────
        for d in page.get_drawings():
            for item in d.get("items", []):
                if item[0] != "l":
                    continue

                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) > 2:
                    continue

                y = p1.y

                # 가장 가까운 텍스트 상태 찾기
                nearest = min(text_states, key=lambda t: abs(t[0] - y), default=None)
                if not nearest or not nearest[1]:
                    continue

                anchor = fitz.Rect(
                    min(p1.x, p2.x) - 1,
                    y - 12,
                    max(p1.x, p2.x) + 1,
                    y + 1,
                )

                text = page.get_text("text", clip=anchor).strip()

                if not text:
                    continue

                if text == "심사관\n파트장\n팀장\n국장":
                    continue

                if text == "(underlined goods/services)":
                    continue

                results.append({
                    "page": page_no,
                    "text": text,
                    "bbox": [round(v, 2) for v in anchor]
                })

    doc.close()
    return results

def extract_underlined_texts_by_flag(pdf_path: str):
    doc = fitz.open(pdf_path)
    results = []

    for page in doc:
        page_no = page.number + 1
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue

            for line in block["lines"]:
                for span in line["spans"]:
                    # 1️⃣ underline flag 확인
                    if not (span["flags"] & 4):
                        continue

                    # 2️⃣ 실제 underline 선 존재 여부 확인
                    if not _is_real_underlined(span, page):
                        continue

                    text = span["text"].strip()
                    if not text:
                        continue

                    results.append({
                        "page": page_no,
                        "text": text,
                        "bbox": [round(v, 2) for v in span["bbox"]]
                    })

    doc.close()
    return results

def apply_underlines_to_result(final_result, underline_texts):
    for ul in underline_texts:
        ul_page = ul["page"]
        ul_bbox = ul["bbox"]
        ul_text = ul["text"].strip()

        if not ul_text:
            continue

        for ground in final_result:
            # earlier_marks
            for em in ground.get("earlier_marks", []):
                for cls in em.get("classes", []):
                    for blk in cls.get("blocks", []):
                        _apply_underline_to_block(blk, ul_page, ul_bbox, ul_text)

            # direct classes
            for cls in ground.get("classes", []):
                for blk in cls.get("blocks", []):
                    _apply_underline_to_block(blk, ul_page, ul_bbox, ul_text)

    return final_result

def merge_blocks_by_mark_and_class(final_result: list[dict]) -> list[dict]:
    merged_results = []

    for ground in final_result:
        new_ground = {
            "ground": ground["ground"],
            "ground_type": ground["ground_type"],
            "ground_number": ground["ground_number"],
            "earlier_marks": [],
            "classes": [],
            "all_goods_rejected": ground.get("all_goods_rejected", False)
        }

        for em in ground.get("earlier_marks", []):
            mark_key = (
                em.get("filing_number"),
                em.get("international_registration_number")
            )

            new_em = {
                "filing_number": em.get("filing_number"),
                "international_registration_number": em.get("international_registration_number"),
                "classes": []
            }

            for cls in em.get("classes", []):
                texts = []
                class_label = cls.get("class")

                for blk in cls.get("blocks", []):
                    texts.append(blk["text"])

                merged_text = _normalize_text(" ".join(texts))

                # ✅ [Class XX] 제거
                merged_text = CLASS_HEADER_RE.sub("", merged_text)

                new_em["classes"].append({
                    "class": class_label,
                    "text": merged_text
                })

            new_ground["earlier_marks"].append(new_em)

        merged_results.append(new_ground)

    return merged_results

def post_process_classes(merged: list[dict]) -> list[dict]:
    for ground in merged:
        for em in ground.get("earlier_marks", []):
            new_classes = []
            for cls in em.get("classes", []):
                new_classes.append(_split_class_text_by_semicolon(cls))
            em["classes"] = new_classes
    return merged

def _find_exclusion_rects(page):
    drawings = page.get_drawings()
    h_lines = []
    v_lines = []

    for d in drawings:
        for item in d.get("items", []):
            if item[0] != "l":
                continue

            p1, p2 = item[1], item[2]

            # 수평선
            if abs(p1.y - p2.y) < 1:
                h_lines.append((min(p1.x, p2.x), max(p1.x, p2.x), p1.y))

            # 수직선
            elif abs(p1.x - p2.x) < 1:
                v_lines.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))

    rects = []

    # 수평선 2개 + 수직선 2개로 사각형 구성
    for x0, x1, y_top in h_lines:
        for x0b, x1b, y_bot in h_lines:
            if y_bot <= y_top:
                continue

            for x_left, y0, y1 in v_lines:
                for x_right, y0b, y1b in v_lines:
                    if x_right <= x_left:
                        continue

                    # 선들이 서로 맞물리는지 확인
                    if (
                        abs(x_left - x0) < 3
                        and abs(x_right - x1) < 3
                        and y0 <= y_top <= y1
                        and y0b <= y_bot <= y1b
                    ):
                        rects.append(
                            fitz.Rect(x_left, y_top, x_right, y_bot)
                        )

    return rects

def _is_inside_any_rect(bbox, rects):
    r = fitz.Rect(bbox)
    for ex in rects:
        if r.intersects(ex):
            return True
    return False

def _apply_underline_to_block(block, ul_page, ul_bbox, ul_text):
    if block["page"] != ul_page:
        return

    if not _bbox_overlap(block["bbox"], ul_bbox):
        return

    block_text = block["text"]

    core, punct = _split_text_and_punct(ul_text)

    if not core:
        return

    # 이미 underline 돼 있으면 skip
    if f"<u>{core}</u>" in block_text:
        return

    # 공백/줄바꿈 정규화 비교
    norm_block = " ".join(block_text.split())
    norm_core  = " ".join(core.split())

    if norm_core not in norm_block:
        return

    # ⭐ 핵심: core만 underline
    block["text"] = block_text.replace(
        core + punct,
        f"<u>{core}</u>{punct}",
        1
    )

def _bbox_overlap(b1, b2, x_tol=2, y_tol=2):
    """
    b1, b2: [x0, y0, x1, y1]
    """
    return not (
        b1[2] < b2[0] - x_tol or
        b1[0] > b2[2] + x_tol or
        b1[3] < b2[1] - y_tol or
        b1[1] > b2[3] + y_tol
    )

def _split_text_and_punct(text: str):
    m = PUNCT_RE.match(text.strip())
    if not m:
        return text, ""
    return m.group(1), m.group(2) or ""

def _is_real_underlined(span, page):
    x0, y0, x1, y1 = span["bbox"]

    # underline은 보통 bbox 바로 아래
    underline_zone = fitz.Rect(
        x0 - 1,
        y1 - 1,
        x1 + 1,
        y1 + 2
    )

    for d in page.get_drawings():
        for item in d.get("items", []):
            if item[0] != "l":
                continue

            p1, p2 = item[1], item[2]

            # 수평선만
            if abs(p1.y - p2.y) < 2:
                line_rect = fitz.Rect(
                    min(p1.x, p2.x),
                    p1.y - 1,
                    max(p1.x, p2.x),
                    p1.y + 1
                )

                if line_rect.intersects(underline_zone):
                    return True

    return False

def _normalize_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def _split_class_text_by_semicolon(cls: dict) -> dict:
    """
    - ; 있으면: ; 기준 분리 후 <u> 포함된 항목만 유지
    - ; 없으면: 그대로 두고 split_mode만 표시
    """
    text = cls["text"]

    # 🔥 세미콜론 없는 경우 → 분기만 표시
    if ";" not in text:
        return {
            "class": cls["class"],
            "text": text,
            "split_mode": "NO_SEMICOLON"
        }

    parts = [p.strip() for p in text.split(";")]

    # 🔥 underline 있는 항목만
    underlined_only = [
        p for p in parts if UNDERLINE_RE.search(p)
    ]

    return {
        "class": cls["class"],
        "text_items": underlined_only,
        "split_mode": "SEMICOLON_UNDERLINED_ONLY"
    }


# =========================
# RUN
# =========================
if __name__ == "__main__":
    pdf_file = "/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/직권가거절통지서샘플/552025075457917-01-복사.pdf"

    ground_blocks = extract_ground_ranges(pdf_file)
    final_result = classify_ground_earlier_class(ground_blocks)
    underline_texts = extract_underlined_texts(pdf_file)

    # fallback
    if not underline_texts:
        underline_texts = extract_underlined_texts_by_flag(pdf_file)

    add_u_tag = apply_underlines_to_result(final_result, underline_texts)

    merged_text = merge_blocks_by_mark_and_class(add_u_tag)
    result = post_process_classes(merged_text)

    print(json.dumps(result, indent=2, ensure_ascii=False))