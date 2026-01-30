import asyncio
import json
import re
from pathlib import Path

import fitz

from container import es_repository

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

TRAILING_PAGE_MARK_RE = re.compile(r"""[\s;,.]*([-–—]\s*\d+\s*[-–—]|\d+\s*/\s*\d+)[\s;,.]*$""", re.VERBOSE)

TRAILING_EXAMPLE_RE = re.compile(
    r"""^\s*([<(\[]\s*ex[ae]mple(s)?\s*[>)\]]|[<(\[]\s*ex[ae]mple(s)?\s*|ex[ae]mple(s)?\s*[>)\]])\s*$""",
    re.IGNORECASE | re.VERBOSE
)

TRAILING_PUNCT_ONLY_RE = re.compile(r"[;,.]+\s*$")

PAGE_NUMBER_ONLY_RE = re.compile(r"""^\s*([-–—]\s*\d+\s*[-–—]|\d+\s*/\s*\d+)\s*$""", re.VERBOSE)


class TestExtractUnderline:
    def __init__(self):
        pass

    async def extract_underline(self, file_path: str, filename: str, trademark_es=None):
        if trademark_es is None:
            trademark_es = await es_repository()
        app_reference_number = filename.split("_")[0]

        ground_blocks = self.extract_ground_ranges(file_path)
        final_result = self.classify_ground_earlier_class(ground_blocks)
        underline_texts = self.extract_underlined_texts(file_path)

        # fallback
        if not underline_texts:
            underline_texts = self.extract_underlined_texts_by_flag(file_path)

        add_u_tag = self.apply_underlines_to_result(final_result, underline_texts)
        merged_text = self.merge_blocks_by_mark_and_class(add_u_tag)
        final_results = await self.post_process_classes(merged_text, app_reference_number, trademark_es)

        return final_results

    def extract_text_items_without_u_tag(self, underline_data: list[dict]) -> list[dict]:
        """
        extract_underline 결과에서 u 태그만 제거하고 데이터 구조는 유지
        """
        import copy
        result = copy.deepcopy(underline_data)

        for ground in result:
            for em in ground.get("earlier_marks", []):
                for cls in em.get("classes", []):
                    clean_items = []
                    for item in cls.get("text_items", []):
                        clean_item = re.sub(r'</?u>', '', item).strip()
                        if clean_item:
                            clean_items.append(clean_item)
                    cls["text_items"] = clean_items

        return result

    def extract_ground_ranges(self, pdf_path: str) -> list[dict]:
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
            exclusion_rects = self._find_exclusion_rects(page)

            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue

                for line in block["lines"]:
                    spans = line["spans"]

                    # line 전체가 exclusion rect와 겹치면 skip
                    if any(self._is_inside_any_rect(s["bbox"], exclusion_rects) for s in spans):
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
                            if self._is_inside_any_rect(s["bbox"], exclusion_rects):
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

    def classify_ground_earlier_class(self, grounds: list[dict]) -> list[dict]:
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

            collecting_applied_goods = False  # 🔥 추가
            applied_goods_blocks = []  # 🔥 추가

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

                # if text.startswith("*"):
                #     continue

                if not text:
                    continue

                # ✅ 페이지 번호만 있는 블록 제거
                if PAGE_NUMBER_ONLY_RE.fullmatch(text):
                    continue

                if TRAILING_EXAMPLE_RE.fullmatch(text.lower()):
                    continue

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

                # ───────── * 기호로 시작하는 항목 → 별도 class로 분리 ─────────
                if text.strip().startswith('*') and current_class:
                    prev_class_no = current_class["class"]
                    flush_class()
                    current_class = {
                        "class": prev_class_no,
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

    def extract_underlined_texts(self, pdf_path: str) -> list[dict]:
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
            text_states = []

            for block in page_dict.get("blocks", []):
                if block["type"] != 0:
                    continue

                for line in block["lines"]:
                    y = line["bbox"][1]
                    text = "".join(span["text"] for span in line["spans"]).strip()

                    if not text:
                        continue

                    # ✅ 페이지 번호만 있는 블록 제거
                    if PAGE_NUMBER_ONLY_RE.fullmatch(text):
                        continue

                    if TRAILING_EXAMPLE_RE.fullmatch(text):
                        continue

                    if not section_started:
                        if START_SECTION_PATTERN.search(text):
                            section_started = True
                        text_states.append((y, False))
                        continue

                    # section_started 이후는 전부 underline 후보로 인정
                    if section_started:
                        text_states.append((y, True))
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

    def extract_underlined_texts_by_flag(self, pdf_path: str):
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
                        if not self._is_real_underlined(span, page):
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

    def apply_underlines_to_result(self, final_result, underline_texts):
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
                            self._apply_underline_to_block(blk, ul_page, ul_bbox, ul_text)

                # direct classes
                for cls in ground.get("classes", []):
                    for blk in cls.get("blocks", []):
                        self._apply_underline_to_block(blk, ul_page, ul_bbox, ul_text)

        return final_result

    def merge_blocks_by_mark_and_class(self, final_result: list[dict]) -> list[dict]:
        merged_results = []

        for ground in final_result:
            new_ground = {
                "ground": ground["ground"],
                "ground_type": ground["ground_type"],
                "ground_number": ground["ground_number"],
                "earlier_marks": [],
                "classes": [],  # 최종적으로 사용 안 함
                "all_goods_rejected": ground.get("all_goods_rejected", False)
            }

            # ==================================================
            # 1️⃣ earlier_marks가 있는 경우 (기존 로직)
            # ==================================================
            if ground.get("earlier_marks"):
                for em in ground["earlier_marks"]:
                    new_em = {
                        "filing_number": em.get("filing_number"),
                        "international_registration_number": em.get("international_registration_number"),
                        "classes": []
                    }

                    for cls in em.get("classes", []):
                        texts = [blk["text"] for blk in cls.get("blocks", [])]
                        merged_text = self._normalize_text(" ".join(texts))
                        merged_text = CLASS_HEADER_RE.sub("", merged_text)
                        merged_text = TRAILING_PAGE_MARK_RE.sub("", merged_text).strip()
                        merged_text = TRAILING_EXAMPLE_RE.sub("", merged_text).strip()
                        merged_text = TRAILING_PUNCT_ONLY_RE.sub("", merged_text).strip()

                        new_em["classes"].append({
                            "class": cls.get("class"),
                            "text": merged_text
                        })

                    new_ground["earlier_marks"].append(new_em)

            # ==================================================
            # 2️⃣ earlier_marks가 없는 경우 → ground.classes 승격
            # ==================================================
            else:
                pseudo_em = {
                    "filing_number": None,
                    "international_registration_number": None,
                    "classes": []
                }

                for cls in ground.get("classes", []):
                    texts = [blk["text"] for blk in cls.get("blocks", [])]

                    merged_text = self._normalize_text(" ".join(texts))
                    merged_text = CLASS_HEADER_RE.sub("", merged_text)
                    merged_text = TRAILING_PAGE_MARK_RE.sub("", merged_text).strip()
                    merged_text = TRAILING_EXAMPLE_RE.sub("", merged_text).strip()
                    merged_text = TRAILING_PUNCT_ONLY_RE.sub("", merged_text).strip()

                    pseudo_em["classes"].append({
                        "class": cls.get("class"),
                        "text": merged_text
                    })

                # ⚠️ classes가 하나라도 있을 때만 추가
                if pseudo_em["classes"]:
                    new_ground["earlier_marks"].append(pseudo_em)

            merged_results.append(new_ground)

        return merged_results

    async def post_process_classes(self, merged: list[dict], app_reference_number, trademark_es) -> list[dict]:
        for ground in merged:
            for em in ground.get("earlier_marks", []):
                new_classes = []
                for cls in em.get("classes", []):
                    text = cls.get("text")
                    if text.startswith("*"):
                        continue
                    new_classes.append(await self.split_class_text(cls, app_reference_number, trademark_es))

                em["classes"] = new_classes
        return merged

    def _find_exclusion_rects(self, page):
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

    def _is_inside_any_rect(self, bbox, rects):
        r = fitz.Rect(bbox)
        for ex in rects:
            if r.intersects(ex):
                return True
        return False

    def _apply_underline_to_block(self, block, ul_page, ul_bbox, ul_text):
        if block["page"] != ul_page:
            return

        if not self._bbox_overlap(block["bbox"], ul_bbox):
            return

        block_text = block["text"]

        core, punct = self._split_text_and_punct(ul_text)

        if not core:
            return

        # 이미 underline 돼 있으면 skip
        if f"<u>{core}</u>" in block_text:
            return

        # 공백/줄바꿈 정규화 비교
        norm_block = " ".join(block_text.split())
        norm_core = " ".join(core.split())

        if norm_core not in norm_block:
            return

        # ⭐ 핵심: core만 underline
        block["text"] = block_text.replace(
            core + punct,
            f"<u>{core}</u>{punct}",
            1
        )

    def _bbox_overlap(self, b1, b2, x_tol=2, y_tol=2):
        """
        b1, b2: [x0, y0, x1, y1]
        """
        return not (
                b1[2] < b2[0] - x_tol or
                b1[0] > b2[2] + x_tol or
                b1[3] < b2[1] - y_tol or
                b1[1] > b2[3] + y_tol
        )

    def _split_text_and_punct(self, text: str):
        m = PUNCT_RE.match(text.strip())
        if not m:
            return text, ""
        return m.group(1), m.group(2) or ""

    def _is_real_underlined(self, span, page):
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

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\n", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    async def split_class_text(self, cls: dict, app_reference_number, trademark_es) -> dict:
        text = cls["text"].strip()

        if ";" in text:
            return self._split_by_semicolon(cls)

        if "," in text:
            return await self._split_by_comma_with_db(cls, app_reference_number, trademark_es)

        return self._split_no_separator(cls)

    def _split_by_semicolon(self, cls: dict) -> dict:
        text = cls["text"]

        # <u> 태그 안의 세미콜론을 임시로 치환
        def replace_semicolons_in_tags(match):
            return match.group(0).replace(';', '\x00')

        text_temp = re.sub(r'<u>.*?</u>', replace_semicolons_in_tags, text, flags=re.DOTALL)
        parts = [p.strip() for p in text_temp.split(";")]
        # 임시 문자를 다시 세미콜론으로 복원
        parts = [p.replace('\x00', ';') for p in parts]

        items = self._post_process_parts(parts)

        return {
            "class": cls["class"],
            "text_items": items,
            "split_mode": "SEMICOLON"
        }

    async def _split_by_comma_with_db(self, cls: dict, app_reference_number, trademark_es) -> dict:
        text = cls["text"]

        if isinstance(text, str):
            split_text = text.split(",")
        else:
            split_text = text

        text_list = []
        for p in split_text:
            p = TRAILING_PAGE_MARK_RE.sub("", p).strip()
            p = TRAILING_EXAMPLE_RE.sub("", p).strip()
            p = TRAILING_PUNCT_ONLY_RE.sub("", p).strip()
            p = self._merge_consecutive_underlines(p)

            if p:
                text_list.append(p)

        text = ", ".join(text_list)

        underline_texts = text.split(',')

        u_tag_texts = []
        for part in underline_texts:

            if "<u>" in part and "</u>" in part:
                u_tag_texts.append(part.strip())

        underline_words = []
        for t in u_tag_texts:
            underline_words.append(self._strip_u_tag(t))

        plain = self._strip_u_tag(text)

        results = []

        full_db_results = await trademark_es.check_international_trademark_data(
            app_reference_number,
            plain
        )

        if full_db_results:
            return {
                "class": cls["class"],
                "text_items": [text],
                "split_mode": "COMMA_DB_FULL_MATCH"
            }

        parts = [p.strip() for p in plain.split(",")]
        for idx, uw in enumerate(underline_words):

            original_u_tag_text = u_tag_texts[idx]

            start_idx = await self._find_start_index_with_db(
                parts, uw, app_reference_number, trademark_es
            )

            if start_idx is None:
                results.append(original_u_tag_text)
                continue

            matched = await self._find_end_index_with_db(
                parts, start_idx, uw, app_reference_number, trademark_es
            )

            if not matched:
                results.append(original_u_tag_text)
                continue

            matched = self._restore_underline(matched, uw)

            results.append(matched)

        return {
            "class": cls["class"],
            "text_items": results,
            "split_mode": "COMMA_DB_MATCH"
        }

    async def _find_start_index_with_db(
            self,
            parts: list[str],
            underline: str,
            app_reference_number: str,
            trademark_es
    ) -> int | None:
        underline_lower = underline.lower()

        underline_idx = None
        for i, part in enumerate(parts):
            if underline_lower in part.lower():
                underline_idx = i
                break

        if underline_idx is None:
            return None

        candidate = parts[underline_idx].strip()
        db_results = await trademark_es.get_trademark_goods_prefix(
            app_reference_number, candidate
        )

        if not db_results:
            return underline_idx

        current_start = underline_idx
        for j in range(underline_idx - 1, -1, -1):
            combined = ", ".join(parts[j:underline_idx + 1])
            db_results = await trademark_es.get_trademark_goods_prefix(
                app_reference_number, combined
            )

            if db_results:
                current_start = j
            else:
                break

        return current_start

    async def _find_end_index_with_db(
            self,
            parts: list[str],
            start_idx: int,
            underline: str,
            app_reference_number: str,
            trademark_es
    ) -> str | None:
        current = parts[start_idx].strip()
        db_results = await trademark_es.get_trademark_goods_suffix(
            app_reference_number, current
        )

        if not db_results:
            return current

        last_matched = current
        for i in range(start_idx + 1, len(parts)):
            current = ", ".join(parts[start_idx:i + 1])
            db_results = await trademark_es.get_trademark_goods_suffix(
                app_reference_number, current
            )

            if db_results:
                last_matched = current
            else:
                break

        return last_matched

    def _split_no_separator(self, cls: dict) -> dict:
        text = cls["text"]

        items = self._post_process_parts([text])

        return {
            "class": cls["class"],
            "text_items": items,
            "split_mode": "NO_SEPARATOR"
        }

    def _post_process_parts(self, parts: list[str]) -> list[str]:
        results = []

        for p in parts:
            if not UNDERLINE_RE.search(p):
                continue
            p = TRAILING_PAGE_MARK_RE.sub("", p).strip()
            p = TRAILING_EXAMPLE_RE.sub("", p).strip()
            p = TRAILING_PUNCT_ONLY_RE.sub("", p).strip()
            p = self._merge_consecutive_underlines(p)

            if p:
                results.append(p)

        return results

    def _merge_consecutive_underlines(self, text: str) -> str:
        tokens = re.findall(r"<u>.*?</u>|[^<]+", text)

        merged = []
        buffer = []

        def flush():
            if not buffer:
                return
            inner = " ".join(
                re.sub(r"</?u>", "", t).strip()
                for t in buffer
            )
            merged.append(f"<u>{inner}</u>")
            buffer.clear()

        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue

            if UNDERLINE_RE.fullmatch(tok):
                buffer.append(tok)
            else:
                flush()
                merged.append(tok)

        flush()

        return re.sub(r"\s+", " ", " ".join(merged)).strip()

    def _strip_u_tag(self, text: str) -> str:
        return re.sub(r"</?u>", "", text).strip()

    def _find_start_index(self, parts: list[str], underline: str, db_results: list[str]) -> int:
        underline = underline.lower()

        for i, part in enumerate(parts):
            if underline not in part.lower():
                continue

            candidate = part.strip()
            if any(db.lower().startswith(candidate.lower()) for db in db_results):
                return i

            combined = candidate
            for j in range(i - 1, -1, -1):
                combined = f"{parts[j].strip()} {combined}"
                if any(db.lower().startswith(combined.lower()) for db in db_results):
                    return j

            return i

        raise RuntimeError("Start index not found")

    def _extract_first_matched_segment(
            self,
            parts: list[str],
            start_idx: int,
            underline: str,
            db_results: list[str]
    ) -> str:
        current = parts[start_idx].strip()

        current_clean = current.rstrip(';,.').strip()
        for db in db_results:
            db_clean = db.rstrip(';,.').strip()
            if current_clean.lower() == db_clean.lower():
                return current

        for i in range(start_idx, len(parts)):
            if i > start_idx:
                current = f"{current} {parts[i].strip()}"

            current_clean = current.rstrip(';,.').strip()
            for db in db_results:
                db_clean = db.rstrip(';,.').strip()
                if current_clean.lower() == db_clean.lower():
                    return current

        raise RuntimeError("No matching segment found")

    def _restore_underline(self, text: str, underline: str) -> str:
        return re.sub(
            rf"\b{re.escape(underline)}\b",
            f"<u>{underline}</u>",
            text,
            flags=re.IGNORECASE
        )


if __name__ == "__main__":
    file_path = '/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/테스트/식별력_1상표1출원.pdf'
    file_name = file_path.split('/')[-1]
    test_extract_underline = TestExtractUnderline()
    result = asyncio.run(test_extract_underline.extract_underline(
        file_path=file_path,
        filename=file_name,
    ))

    print(json.dumps(result, indent=2, ensure_ascii=False))
