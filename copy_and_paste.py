"""
통합 로직:
- ';'이 있으면: ';'과 '.' 기준으로 개별 상품 분리, 밑줄 있는 상품만 추출
- ';'이 없으면: ','와 '.'로 구분된 전체 문자열 유지, 밑줄 부분만 <u> 태그 적용
PDF에서 밑줄 친 텍스트를 추출하고
해당 밑줄이 속한 상표(Filing number/International registration number)와 연결
"""

import json
import re
import fitz
import sys
from pathlib import Path

# 데이터 추출 종료 패턴: "10. Guidance:" 또는 "10. Guidance for the response:" 등
GUIDANCE_END_PATTERN = re.compile(
    r'10\.\s*Guidance(?:\s+for\s+the\s+response)?\s*:',
    re.IGNORECASE
)


def extract_trademark_sections(pdf_path):
    """
    PDF에서 'Information concerning the earlier mark' 섹션을 기준으로
    각 상표(Earlier Mark)의 범위를 추출하는 함수
    """

    doc = fitz.open(pdf_path)
    sections = []
    all_blocks = []

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if "lines" not in block:
                continue

            block_text = ""
            for line in block["lines"]:
                for span in line["spans"]:
                    block_text += span["text"] + " "

            block_text = block_text.strip()

            block_info = {
                "page": page_num + 1,
                "y0": block["bbox"][1],
                "y1": block["bbox"][3],
                "text": block_text
            }

            all_blocks.append(block_info)

    section_starts = []

    for idx, block in enumerate(all_blocks):
        text = block["text"]
        text_cleaned = text.replace("□", "").replace("☐", "").strip()

        match = re.search(
            r"Information\s+concerning\s+the\s+earlier\s+mark\s*\((\d+)\)",
            text_cleaned,
            re.IGNORECASE
        )

        if match:
            mark_number = int(match.group(1))
            section_starts.append({
                "index": idx,
                "mark_number": mark_number,
                "page": block["page"],
                "y": block["y0"]
            })
            continue

        match = re.search(
            r"Information\s+concerning\s+the\s+earlier\s+mark\s*$",
            text_cleaned,
            re.IGNORECASE
        )

        if match:
            section_starts.append({
                "index": idx,
                "mark_number": 1,
                "page": block["page"],
                "y": block["y0"]
            })

    if not section_starts:
        # Information concerning the earlier mark 패턴이 없으면
        # filing_number와 international_registration을 None으로 처리
        doc.close()

        return [{
            "mark_number": 1,
            "filing_number": None,
            "international_registration": None,
            "page_start": 1,
            "page_end": all_blocks[-1]["page"] if all_blocks else 1,
            "y_start": 0,
            "y_end": float('inf')
        }]

    for i, start in enumerate(section_starts):
        if i + 1 < len(section_starts):
            end_idx = section_starts[i + 1]["index"]
            end_page = section_starts[i + 1]["page"]
            end_y = section_starts[i + 1]["y"]
        else:
            end_idx = len(all_blocks)
            end_page = all_blocks[-1]["page"]
            end_y = all_blocks[-1]["y1"]

        section_text = " ".join(
            all_blocks[j]["text"] for j in range(start["index"], end_idx)
        )

        filing_match = re.search(r"Filing\s+number\s*:\s*(\d+)", section_text)
        filing_number = filing_match.group(1) if filing_match else None

        ir_match = re.search(
            r"International\s+registration\s+number\s*:\s*(\d+)",
            section_text,
            re.IGNORECASE
        )
        international_registration = ir_match.group(1) if ir_match else None

        sections.append({
            "mark_number": start["mark_number"],
            "filing_number": filing_number,
            "international_registration": international_registration,
            "page_start": start["page"],
            "page_end": end_page,
            "y_start": start["y"],
            "y_end": end_y
        })

    doc.close()
    return sections

# ============================================================
# 사각형/표 영역 감지 함수
# ============================================================
def find_rect_regions(page):
    """
    페이지에서 사각형/표 영역을 찾아서 반환
    - "re" (rect) 타입의 drawings
    - 4개의 선으로 구성된 닫힌 경로
    """
    drawings = page.get_drawings()
    rects = []

    for d in drawings:
        items = d.get("items", [])

        # "re" (rectangle) 타입 찾기
        for item in items:
            if item[0] == "re":
                rect = item[1]  # fitz.Rect 객체
                # 너무 작은 사각형은 제외 (최소 50x20)
                if rect.width > 50 and rect.height > 20:
                    rects.append(rect)

        # 4개의 선으로 구성된 닫힌 경로 찾기
        if len(items) >= 4:
            h_lines = []  # 수평선
            v_lines = []  # 수직선

            for item in items:
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) < 2:  # 수평선
                        h_lines.append((min(p1.x, p2.x), max(p1.x, p2.x), p1.y))
                    elif abs(p1.x - p2.x) < 2:  # 수직선
                        v_lines.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))

            # 2개 이상의 수평선과 2개 이상의 수직선이 있으면 표/사각형으로 간주
            if len(h_lines) >= 2 and len(v_lines) >= 2:
                x_min = min(l[0] for l in h_lines)
                x_max = max(l[1] for l in h_lines)
                y_min = min(l[2] for l in h_lines)
                y_max = max(l[2] for l in h_lines)

                if (x_max - x_min) > 50 and (y_max - y_min) > 20:
                    rects.append(fitz.Rect(x_min, y_min, x_max, y_max))

    return rects

def is_inside_rect(line, rects, margin=5):
    """밑줄의 y좌표가 사각형/표 영역 내에 있는지 확인 (x좌표 무관하게 y범위만 체크)"""
    line_y = line["y"]

    for rect in rects:
        # y좌표가 사각형 영역 내에 있으면 제외 (표/박스 내부의 모든 데이터 제외)
        if rect.y0 - margin <= line_y <= rect.y1 + margin:
            return True

    return False

# ============================================================
# SEMICOLON 방식: ';'과 '.' 기준 개별 상품 분리
# ============================================================
def extract_underlined_with_positions_semicolon(pdf_path):
    """
    ';' 기준 PDF용: 밑줄 텍스트를 개별 상품으로 추출
    """
    doc = fitz.open(pdf_path)
    results = []
    last_class = None  # 마지막으로 발견한 class 값 저장
    guidance_found = False  # "10. Guidance" 패턴 발견 여부

    for page_num, page in enumerate(doc):
        if guidance_found:
            break

        # 페이지에서 "10. Guidance" 패턴의 y좌표 찾기
        guidance_y = None
        page_text_dict = page.get_text("dict")
        for block in page_text_dict["blocks"]:
            if "lines" not in block:
                continue
            for line_obj in block["lines"]:
                line_text = "".join(span["text"] for span in line_obj["spans"])
                if GUIDANCE_END_PATTERN.search(line_text):
                    guidance_y = block["bbox"][1]  # 블록의 y 시작 좌표
                    guidance_found = True
                    break
            if guidance_y is not None:
                break

        drawings = page.get_drawings()
        lines = []

        # 사각형/표 영역 찾기
        rect_regions = find_rect_regions(page)

        for d in drawings:
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]

                    if abs(p1.y - p2.y) < 2:
                        length = abs(p2.x - p1.x)

                        if 10 < length < 500:
                            line_info = {
                                "y": p1.y,
                                "x0": min(p1.x, p2.x),
                                "x1": max(p1.x, p2.x),
                            }

                            # 사각형/표 내부의 밑줄은 제외
                            if not is_inside_rect(line_info, rect_regions):
                                lines.append(line_info)

        # y좌표 순으로 정렬 (위에서 아래로)
        lines = sorted(lines, key=lambda x: x["y"])

        for line in lines:
            # "10. Guidance" 이후의 밑줄은 무시
            if guidance_y is not None and line["y"] >= guidance_y:
                break

            anchor_rect = fitz.Rect(
                line["x0"] - 1,
                line["y"] - 12,
                line["x1"] + 1,
                line["y"] + 1,
            )

            raw_text = page.get_text("text", clip=anchor_rect)
            if raw_text.startswith(('심사관', '파트장', '팀장', '국장')):
                continue

            anchor_text = " ".join(raw_text.strip().split())

            if not anchor_text:
                continue

            full_rect = fitz.Rect(
                0,
                line["y"] - 12,
                page.rect.width,
                line["y"] + 1,
            )

            full_raw_text = page.get_text("text", clip=full_rect)
            full_text = " ".join(full_raw_text.strip().split())

            if full_text.startswith('※ Note :') or full_text.startswith('(https://'):
                continue

            if not full_text:
                continue

            # Class 정보 추출 - 현재 라인에서 먼저 찾기
            match = re.search(r'\[Class\s+(\d+)\]', full_text, re.IGNORECASE)
            class_num = match.group(1) if match else None

            # 현재 라인에 없으면 위쪽 영역에서 찾기 (줄바꿈된 경우)
            if not class_num:
                extended_rect = fitz.Rect(
                    0,
                    line["y"] - 30,  # 위쪽으로 더 넓게
                    page.rect.width,
                    line["y"] + 1,
                )
                extended_text = page.get_text("text", clip=extended_rect)
                extended_text = " ".join(extended_text.strip().split())
                match = re.search(r'\[Class\s+(\d+)\]', extended_text, re.IGNORECASE)
                class_num = match.group(1) if match else None

            # class를 찾았으면 last_class 업데이트, 못 찾았으면 last_class 사용
            if class_num:
                last_class = class_num
            else:
                class_num = last_class

            # 정규화
            normalized_text = normalize_for_compare(anchor_text)

            if should_exclude_underlined_text(normalized_text):
                continue

            # 끝의 . 만 제거 (; , 는 유지하여 merge_multiline_underlines에서 분리 기준으로 사용)
            underline_core = re.sub(r"[.]\s*$", "", normalized_text).strip()

            if not underline_core:
                continue

            tagged_text = f"<u>{underline_core}</u>"

            result_item = {
                "page": page_num + 1,
                "y": line["y"],
                "text": underline_core,  # ; , 는 유지됨
                "full_text": full_text,
                "tagged_text": tagged_text,
                "class": class_num,
            }

            results.append(result_item)

    print(results)

    doc.close()
    return results

def extract_underlines_only(pdf_path):
    """PDF에서 밑줄(수평선)과 해당 텍스트 추출"""
    doc = fitz.open(pdf_path)
    underlines = []
    guidance_found = False  # "10. Guidance" 패턴 발견 여부

    for page_num, page in enumerate(doc):
        if guidance_found:
            break

        # 페이지에서 "10. Guidance" 패턴의 y좌표 찾기
        guidance_y = None
        page_text_dict = page.get_text("dict")
        for block in page_text_dict["blocks"]:
            if "lines" not in block:
                continue
            for line_obj in block["lines"]:
                line_text = "".join(span["text"] for span in line_obj["spans"])
                if GUIDANCE_END_PATTERN.search(line_text):
                    guidance_y = block["bbox"][1]
                    guidance_found = True
                    break
            if guidance_y is not None:
                break

        drawings = page.get_drawings()

        for d in drawings:
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]

                    # "10. Guidance" 이후의 밑줄은 무시
                    if guidance_y is not None and p1.y >= guidance_y:
                        continue

                    if abs(p1.y - p2.y) < 2:
                        length = abs(p2.x - p1.x)

                        if 10 < length < 500:
                            # 밑줄 위의 텍스트도 추출
                            clip_rect = fitz.Rect(
                                min(p1.x, p2.x) - 1,
                                p1.y - 12,
                                max(p1.x, p2.x) + 1,
                                p1.y + 1
                            )
                            text = page.get_text("text", clip=clip_rect).strip()
                            text = " ".join(text.split())
                            # 끝의 구두점 제거
                            text = text.rstrip(',;.')

                            underlines.append({
                                "page": page_num + 1,
                                "y": p1.y,
                                "x0": min(p1.x, p2.x),
                                "x1": max(p1.x, p2.x),
                                "text": text,
                            })

    doc.close()
    print(underlines)
    return underlines

# ============================================================
# COMMA 방식: 전체 문자열 유지, 밑줄 부분만 <u> 태그
# ============================================================
def extract_goods_with_spans_comma(pdf_path, underlines):
    """
    ',' 기준 PDF용: 전체 상품 문자열에서 밑줄 부분만 <u> 태그 적용
    '.'으로만 분리 (','는 분리하지 않음)
    """
    doc = fitz.open(pdf_path)
    results = []

    # 다양한 Goods/Services 패턴 지원
    # - Goods/Services of the applied-for mark in relation to this ground
    # - Goods of the proposed mark refused by this ground for refusal
    # - Goods of the proposed mark refused under this ground
    ANCHOR_PATTERN = re.compile(
        r"Goods(?:/Services)?\s+of\s+the\s+(?:applied[- ]for|proposed)\s+mark",
        re.IGNORECASE
    )

    PAGE_NUM_PATTERN = re.compile(r'^\s*-\s*\d+\s*-\s*$')

    # "all the designated goods/services" 패턴 (다양한 변형 포함)
    ALL_DESIGNATED_PATTERN = re.compile(
        r'[\'\""\']?\s*all\s*[\'\""\']?\s+the\s+designated\s+(goods\s*/\s*services|goods|services)',
        re.IGNORECASE
    )

    def get_underlined_texts_for_page(page, page_num):
        """페이지에서 밑줄 바로 위의 텍스트 추출"""
        underlined_texts = []
        page_underlines = [ul for ul in underlines if ul["page"] == page_num]

        for ul in page_underlines:
            clip_rect = fitz.Rect(
                ul["x0"] - 1,
                ul["y"] - 12,
                ul["x1"] + 1,
                ul["y"] + 1
            )
            text = page.get_text("text", clip=clip_rect).strip()
            text = " ".join(text.split())

            # 끝의 구두점(, ; .) 제거 - <u> 태그 밖으로 이동시키기 위함
            text = text.rstrip(',;.')

            if text:
                if should_exclude_underlined_text(text):
                    continue

                underlined_texts.append({
                    "text": text,
                    "y": ul["y"],
                    "x0": ul["x0"],
                    "x1": ul["x1"]
                })

        return underlined_texts

    def apply_underline_tags(full_text, underlined_texts):
        """전체 텍스트에서 밑줄 텍스트에만 <u> 태그 적용"""
        if not underlined_texts:
            return full_text

        tagged_text = full_text

        sorted_ul_texts = sorted(underlined_texts, key=lambda x: len(x["text"]), reverse=True)

        for ul in sorted_ul_texts:
            ul_text = ul["text"]
            if not ul_text:
                continue

            if f"<u>{ul_text}</u>" in tagged_text:
                continue

            if ul_text in tagged_text:
                pattern = re.compile(re.escape(ul_text))
                matches = list(pattern.finditer(tagged_text))

                # 앞에서부터 매칭 (밑줄은 보통 첫 번째 출현에 있음)
                for match in matches:
                    start, end = match.start(), match.end()

                    before = tagged_text[:start]
                    if before.count("<u>") > before.count("</u>"):
                        continue

                    tagged_text = tagged_text[:start] + f"<u>{ul_text}</u>" + tagged_text[end:]
                    break

        return tagged_text

    buffer_texts = []
    buffer_page = None
    buffer_y0 = float('inf')
    buffer_y1 = 0
    buffer_underlined_texts = []
    buffer_class = None
    last_class = None  # 마지막으로 발견한 class 값 저장

    def flush_buffer():
        nonlocal buffer_texts, buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts, buffer_class, last_class

        if not buffer_texts:
            return

        full_text = " ".join(buffer_texts)
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        if full_text:
            tagged_text = apply_underline_tags(full_text, buffer_underlined_texts)

            # [Class XX] 추출
            class_match = re.search(r'\[Class\s+(\d+)\]', full_text, re.IGNORECASE)
            if class_match:
                class_num = class_match.group(1)
                last_class = class_num  # 새 class 발견 시 저장
            elif buffer_class:
                class_num = buffer_class
            else:
                class_num = last_class  # 못 찾으면 마지막 class 사용

            results.append({
                "page": buffer_page,
                "text": full_text,
                "tagged_text": tagged_text,
                "y0": buffer_y0,
                "y1": buffer_y1,
                "class": class_num,
            })

        buffer_texts = []
        buffer_y0 = float('inf')
        buffer_y1 = 0
        buffer_underlined_texts = []
        buffer_class = None

    def add_to_buffer(text, y0, y1, page, page_underlined_texts):
        nonlocal buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts, buffer_class, last_class

        buffer_texts.append(text)
        buffer_page = page
        buffer_y0 = min(buffer_y0, y0)
        buffer_y1 = max(buffer_y1, y1)

        # [Class XX] 추출
        class_match = re.search(r'\[Class\s+(\d+)\]', text, re.IGNORECASE)
        if class_match:
            buffer_class = class_match.group(1)
            last_class = buffer_class  # 마지막 class 값 업데이트

        for ul in page_underlined_texts:
            if y0 - 5 <= ul["y"] <= y1 + 5:
                if ul not in buffer_underlined_texts:
                    buffer_underlined_texts.append(ul)

    after_anchor = False
    guidance_found = False  # "10. Guidance" 패턴 발견 여부

    for page_num, page in enumerate(doc):
        if guidance_found:
            break

        text_dict = page.get_text("dict")
        page_underlined_texts = get_underlined_texts_for_page(page, page_num + 1)

        for block in text_dict["blocks"]:
            if guidance_found:
                break

            if "lines" not in block:
                continue

            for line_obj in block["lines"]:
                if guidance_found:
                    break

                for span in line_obj["spans"]:
                    txt = span["text"]
                    bbox = span["bbox"]

                    if not txt.strip():
                        continue

                    if PAGE_NUM_PATTERN.match(txt.strip()):
                        continue

                    # "10. Guidance" 패턴 발견 시 추출 종료
                    if GUIDANCE_END_PATTERN.search(txt):
                        flush_buffer()
                        guidance_found = True
                        break

                    if ANCHOR_PATTERN.search(txt):
                        after_anchor = True
                        colon_idx = txt.find(":")
                        if colon_idx != -1 and colon_idx < len(txt) - 1:
                            after_colon = txt[colon_idx + 1:].strip()
                            if after_colon:
                                if '.' in after_colon:
                                    parts = re.split(r'([.])', after_colon)
                                    for part in parts:
                                        if not part:
                                            continue
                                        if part == '.':
                                            flush_buffer()
                                            after_anchor = False
                                        else:
                                            add_to_buffer(part, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
                                else:
                                    add_to_buffer(after_colon, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
                                    # "all the designated" 패턴 체크 - ':'뒤에 바로 있는 경우
                                    current_buffer_text = " ".join(buffer_texts)
                                    if ALL_DESIGNATED_PATTERN.search(current_buffer_text):
                                        flush_buffer()
                                        after_anchor = False
                        continue

                    if not after_anchor:
                        continue

                    # '.'으로만 분리 (','는 분리 안함)
                    if '.' in txt:
                        parts = re.split(r'([.])', txt)
                        for part in parts:
                            if not part:
                                continue
                            if part == '.':
                                flush_buffer()
                                after_anchor = False
                            else:
                                add_to_buffer(part, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
                    else:
                        add_to_buffer(txt, bbox[1], bbox[3], page_num + 1, page_underlined_texts)

                    # "all the designated goods/services" 패턴 체크 - '.'이 없어도 flush
                    current_buffer_text = " ".join(buffer_texts)
                    if ALL_DESIGNATED_PATTERN.search(current_buffer_text):
                        flush_buffer()
                        after_anchor = False

    flush_buffer()
    doc.close()
    print(results)
    return results

# ============================================================
# 메인 처리 함수
# ============================================================
def detect_delimiter_for_goods_text(goods_text):
    """
    특정 Goods/Services 텍스트의 구분자 타입 판단
    - 이제 모든 구분자(;, ., ,)를 동일하게 처리하므로 항상 'semicolon' 반환
    """
    return 'semicolon'

def match_underlines_to_sections_semicolon(sections, underlines):
    """섹션에 밑줄 매칭 (semicolon 방식)"""
    results = []

    for section in sections:
        goods_list = []

        section_underlines = []
        for u in underlines:
            if not (section["page_start"] <= u["page"] <= section["page_end"]):
                continue
            if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
                continue
            if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
                continue

            section_underlines.append(u)

        section_underlines = merge_multiline_underlines(section_underlines)

        for u in section_underlines:
            ALL_DESIGNATED_PATTERN = re.compile(
                r'(?i)[\'\""\"]?\s*all\s*[\'\""\"]?\s+the\s+designated\s+(goods\s*/\s*services|goods|services)',
                re.VERBOSE
            )
            if ALL_DESIGNATED_PATTERN.search(u.get("full_text", "")):
                g = "<u>all the designated goods/services</u>"
                goods_list.append({
                    "class": u.get("class"),
                    "goods": g
                })
                continue

            goods = extract_goods_from_tagged_text(u["tagged_text"])
            full_text = u.get("full_text", "")
            # ; 이 있으면 ; 로만 분리, 없으면 , 로 분리
            if ';' in full_text:
                full_goods_parts = [
                    p.strip()
                    for p in re.split(r"[;.]", full_text)
                    if p.strip()
                ]
            else:
                full_goods_parts = [
                    p.strip()
                    for p in re.split(r"[,.]", full_text)
                    if p.strip()
                ]

            for g in goods:
                core = re.sub(r"</?u>", "", g).strip()

                extended = None
                standalone_exists = any(
                    p.strip().lower() == core.lower()
                    for p in full_goods_parts
                )

                for part in full_goods_parts:
                    if (
                            part.lower().startswith(core.lower() + " ")
                            and not standalone_exists
                    ):
                        extended = part
                        break

                if extended:
                    goods_list.append({
                        "class": u.get("class"),
                        "goods": extended.replace(
                            core,
                            f"<u>{core}</u>",
                            1
                        )
                    })
                else:
                    goods_list.append({
                        "class": u.get("class"),
                        "goods": g
                    })

        results.append({
            "mark_number": section.get("mark_number"),
            "filing_number": section["filing_number"],
            "international_registration": section["international_registration"],
            "underlined_goods": goods_list
        })

    for r in results:
        for item in r["underlined_goods"]:
            item["goods"] = clean_goods_text(item["goods"])

    return results

def clean_goods_text(goods: str) -> str:
    """최종 결과용 goods 문자열 정리"""
    if not goods:
        return goods

    goods = re.sub(
        r"^\*?\s*Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground:\s*",
        "",
        goods,
        flags=re.IGNORECASE
    )

    goods = re.sub(r"\s*\[\s*Class\s*\d+\s*\]\s*", "", goods, flags=re.IGNORECASE)
    goods = re.sub(r"<u>\s+", "<u>", goods)
    goods = re.sub(r"\s{2,}", " ", goods)

    return goods.strip()

def normalize_for_compare(text: str) -> str:
    """상품 비교용 정규화"""
    if not text:
        return ""

    text = re.sub(
        r"^\*?\s*Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground:\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(r"\[\s*Class\s*\d+\s*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()

def should_exclude_underlined_text(text: str) -> bool:
    """밑줄 텍스트가 상품 정보가 아닌 경우 제외"""
    stripped = text.strip()

    # << ... >> 패턴 (정보 박스)
    if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
        return True

    # << 로 시작하는 텍스트
    if stripped.startswith("<<"):
        return True

    # → 포함 (표 형식 데이터)
    if "→" in stripped:
        return True

    # 연락처 정보
    if re.search(r"\b(Fax|Tel\.?|Telephone|E-mail|Email)\b", stripped, re.IGNORECASE):
        return True

    if "@" in stripped:
        return True

    # 심사관 등 직함
    if stripped in ["심사관 파트장 팀장 국장", "심사관 팀장 국장"]:
        return True

    if stripped.startswith(('심사관', '파트장', '팀장', '국장')):
        return True

    # 안내 문구
    if re.search(r"underlined goods", stripped, re.IGNORECASE):
        return True

    if re.search(r"Ministry of Intellectual Property|MOIP", stripped, re.IGNORECASE):
        return True

    if re.search(r"<<\s*Information\s*>>", stripped, re.IGNORECASE):
        return True

    return False

def merge_multiline_underlines(underlines, y_gap=20):
    """줄바꿈된 underline을 하나의 상품으로 병합"""
    underlines = sorted(underlines, key=lambda x: (x["page"], x["y"]))
    merged = []

    # "all the designated goods/services" 패턴 - 병합하지 않음
    ALL_DESIGNATED_PATTERN = re.compile(
        r'[\'\""\']?\s*all\s*[\'\""\']?\s+the\s+designated\s+(goods\s*/\s*services|goods|services)',
        re.IGNORECASE
    )

    buffer = None

    for u in underlines:
        if buffer is None:
            buffer = u.copy()
            continue

        same_page = buffer["page"] == u["page"]
        close_y = abs(u["y"] - buffer["y"]) < y_gap

        # ; . 로 끝나면 별도 상품으로 분리
        # , 는 ;이 없을 때만 분리 기준으로 사용
        text_strip = buffer["text"].strip()
        if ';' in text_strip:
            no_end = not text_strip.endswith((';', '.'))
        else:
            no_end = not text_strip.endswith((';', '.', ','))

        # "all the designated" 패턴이 있으면 병합하지 않음 (완결된 표현)
        is_all_designated = ALL_DESIGNATED_PATTERN.search(buffer["text"])

        if same_page and close_y and no_end and not is_all_designated:
            buffer["text"] = buffer["text"].rstrip(';') + " " + u["text"].lstrip()

            buffer["tagged_text"] = (
                buffer["tagged_text"].replace("</u>", "") +
                " " +
                u["tagged_text"].replace("<u>", "")
            )

            buffer["y"] = u["y"]
        else:
            merged.append(buffer)
            buffer = u.copy()

    if buffer:
        merged.append(buffer)

    return merged

def extract_goods_from_tagged_text(tagged_text: str) -> list:
    """<u>...</u> 블록에서 상품 추출 (; 우선, 없으면 , 기준 분리)"""
    goods = []
    underline_blocks = re.findall(r"<u>(.*?)</u>", tagged_text)

    for block in underline_blocks:
        # ; 이 있으면 ; 로만 분리, 없으면 , 로 분리
        if ';' in block:
            parts = [p.strip() for p in re.split(r";", block) if p.strip()]
        else:
            parts = [p.strip() for p in re.split(r",", block) if p.strip()]

        for part in parts:
            goods.append(f"<u>{part}</u>")

    return goods


def process_pdf(pdf_path):
    """
    PDF 처리 메인 함수
    - 각 Goods/Services 영역마다 구분자 타입을 개별 판단
    - semicolon: 밑줄 있는 상품만 개별 추출
    - comma: 전체 텍스트 유지, 밑줄 부분만 <u> 태그
    """
    sections = extract_trademark_sections(pdf_path)

    # 두 방식 모두 실행하여 결과 준비
    underlines_semicolon = extract_underlined_with_positions_semicolon(pdf_path)
    underlines_only = extract_underlines_only(pdf_path)
    tagged_results_comma = extract_goods_with_spans_comma(pdf_path, underlines_only)

    # 각 섹션별로 적절한 방식 선택
    final_results = []

    for section in sections:
        # 해당 섹션의 Goods/Services 텍스트에서 구분자 판단
        section_goods_text = ""

        # semicolon 결과에서 해당 섹션의 텍스트 수집
        for u in underlines_semicolon:
            if not (section["page_start"] <= u["page"] <= section["page_end"]):
                continue
            if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
                continue
            if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
                continue
            section_goods_text += u.get("full_text", "") + " "

        # comma 결과에서도 텍스트 수집
        for tr in tagged_results_comma:
            tr_page = tr["page"]
            tr_y0 = tr["y0"]
            if not (section["page_start"] <= tr_page <= section["page_end"]):
                continue
            if tr_page == section["page_start"] and tr_y0 < section["y_start"]:
                continue
            if tr_page == section["page_end"] and tr_y0 >= section["y_end"]:
                continue
            section_goods_text += tr.get("text", "") + " "

        delimiter_type = detect_delimiter_for_goods_text(section_goods_text)

        if delimiter_type == 'semicolon':
            # semicolon 방식: 밑줄 있는 상품만 개별 추출
            section_underlines = []
            for u in underlines_semicolon:
                if not (section["page_start"] <= u["page"] <= section["page_end"]):
                    continue
                if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
                    continue
                if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
                    continue
                section_underlines.append(u)

            result = match_underlines_to_sections_semicolon([section], section_underlines)
            if result and result[0].get("underlined_goods"):
                for goods_item in result[0]["underlined_goods"]:
                    final_results.append({
                        "filing_number": section["filing_number"],
                        "international_registration_number": section["international_registration"],
                        "class": goods_item.get("class"),
                        "goods": goods_item.get("goods")
                    })
        else:
            # comma 방식: 전체 텍스트 유지, 밑줄 부분만 <u> 태그
            matched_list = []
            for tr in tagged_results_comma:
                tr_page = tr["page"]
                tr_y0 = tr["y0"]

                if not (section["page_start"] <= tr_page <= section["page_end"]):
                    continue
                if tr_page == section["page_start"] and tr_y0 < section["y_start"]:
                    continue
                if tr_page == section["page_end"] and tr_y0 >= section["y_end"]:
                    continue

                matched_list.append(tr)

            # 각 항목을 단순화된 형태로 추가
            for item in matched_list:
                tagged_text = clean_goods_text(item.get("tagged_text", ""))
                final_results.append({
                    "filing_number": section["filing_number"],
                    "international_registration_number": section["international_registration"],
                    "class": item.get("class"),
                    "goods": tagged_text
                })

    for f in final_results:
        print(json.dumps(f, indent=2, ensure_ascii=False))

    return final_results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/직권가거절통지서샘플/552026004951830-01-복사.pdf"

    if not Path(pdf_path).exists():
        print(f"파일 없음: {pdf_path}")
        sys.exit(1)

    print("=" * 80)
    print(f"\n파일 분석 중: {pdf_path}\n")

    data = process_pdf(pdf_path)
