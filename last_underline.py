"""
통합 로직:
- ';'이 있으면: ';'과 '.' 기준으로 개별 상품 분리, 밑줄 있는 상품만 추출
- ';'이 없으면: ','와 '.'로 구분된 전체 문자열 유지, 밑줄 부분만 <u> 태그 적용
PDF에서 밑줄 친 텍스트를 추출하고
해당 밑줄이 속한 상표(Filing number/International registration number)와 연결
"""

import re
import fitz
import sys
from pathlib import Path


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
        full_text = " ".join([block["text"] for block in all_blocks])

        filing_match = re.search(r"Filing number\s*:\s*(\d+)", full_text)
        filing_number = filing_match.group(1) if filing_match else None

        ir_match = re.search(
            r"International\s+(?:Registration|registration)[/\s]+"
            r"Subsequent\s+Designation\s+No[.\s]*:?\s*(\d+)",
            full_text
        )
        international_registration = ir_match.group(1) if ir_match else None

        doc.close()

        return [{
            "mark_number": 1,
            "filing_number": filing_number,
            "international_registration": international_registration,
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


def extract_underlines_only(pdf_path):
    """PDF에서 밑줄(수평선)만 추출"""
    doc = fitz.open(pdf_path)
    underlines = []

    for page_num, page in enumerate(doc):
        drawings = page.get_drawings()

        for d in drawings:
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]

                    if abs(p1.y - p2.y) < 2:
                        length = abs(p2.x - p1.x)

                        if 10 < length < 500:
                            underlines.append({
                                "page": page_num + 1,
                                "y": p1.y,
                                "x0": min(p1.x, p2.x),
                                "x1": max(p1.x, p2.x),
                            })

    doc.close()
    return underlines


def detect_delimiter_type(pdf_path):
    """
    PDF에서 Goods/Services 영역의 구분자 타입 감지
    - ';'이 있으면 'semicolon' 반환
    - ';'이 없고 ','가 있으면 'comma' 반환
    """
    doc = fitz.open(pdf_path)

    anchor_pattern = re.compile(
        r"Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground",
        re.IGNORECASE
    )

    goods_text = ""
    after_anchor = False

    for page in doc:
        text_dict = page.get_text("dict")

        for block in text_dict["blocks"]:
            if "lines" not in block:
                continue

            for line_obj in block["lines"]:
                for span in line_obj["spans"]:
                    txt = span["text"]

                    if anchor_pattern.search(txt):
                        after_anchor = True
                        colon_idx = txt.find(":")
                        if colon_idx != -1:
                            goods_text += txt[colon_idx + 1:]
                        continue

                    if after_anchor:
                        goods_text += txt
                        if '.' in txt:
                            break

            if after_anchor and '.' in goods_text:
                break
        if after_anchor and '.' in goods_text:
            break

    doc.close()

    if ';' in goods_text:
        return 'semicolon'
    else:
        return 'comma'


def should_exclude_underlined_text(text: str) -> bool:
    """밑줄 텍스트가 상품 정보가 아닌 경우 제외"""
    stripped = text.strip()

    if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
        return True

    if re.search(r"\b(Fax|Tel\.?|Telephone|E-mail|Email)\b", stripped, re.IGNORECASE):
        return True

    if "@" in stripped:
        return True

    if stripped in ["심사관 파트장 팀장 국장", "심사관 팀장 국장"]:
        return True

    if stripped.startswith(('심사관', '파트장', '팀장', '국장')):
        return True

    if re.search(r"underlined goods", stripped, re.IGNORECASE):
        return True

    return False


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


# ============================================================
# SEMICOLON 방식: ';'과 '.' 기준 개별 상품 분리
# ============================================================

def extract_underlined_with_positions_semicolon(pdf_path):
    """
    ';' 기준 PDF용: 밑줄 텍스트를 개별 상품으로 추출
    """
    doc = fitz.open(pdf_path)
    results = []

    for page_num, page in enumerate(doc):
        drawings = page.get_drawings()
        lines = []

        for d in drawings:
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]

                    if abs(p1.y - p2.y) < 2:
                        length = abs(p2.x - p1.x)

                        if 10 < length < 500:
                            lines.append({
                                "y": p1.y,
                                "x0": min(p1.x, p2.x),
                                "x1": max(p1.x, p2.x),
                            })

        for line in lines:
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

            if not full_text:
                continue

            # Class 정보 추출
            match = re.search(r'\[Class\s+(\d+)\]', full_text, re.IGNORECASE)
            class_num = match.group(1) if match else None

            # 정규화
            normalized_text = normalize_for_compare(anchor_text)

            if should_exclude_underlined_text(normalized_text):
                continue

            # delimiter 제거
            underline_core = re.sub(r"[;.]\s*$", "", normalized_text).strip()
            compare_underline = normalize_for_compare(underline_core)

            # full_text → 상품 단위 분리
            goods_parts = [
                p.strip()
                for p in re.split(r"[;.]", full_text)
                if p.strip()
            ]

            tagged_text = None

            for part in goods_parts:
                compare_part = normalize_for_compare(part)

                if compare_part == compare_underline:
                    tagged_text = f"<u>{compare_part}</u>"
                    break

            if not tagged_text:
                tagged_text = f"<u>{underline_core}</u>"

            result_item = {
                "page": page_num + 1,
                "y": line["y"],
                "text": normalized_text,
                "full_text": full_text,
                "tagged_text": tagged_text,
                "class": class_num,
            }

            results.append(result_item)

    doc.close()
    return results


def merge_multiline_underlines(underlines, y_gap=20):
    """줄바꿈된 underline을 하나의 상품으로 병합"""
    underlines = sorted(underlines, key=lambda x: (x["page"], x["y"]))
    merged = []

    buffer = None

    for u in underlines:
        if buffer is None:
            buffer = u.copy()
            continue

        same_page = buffer["page"] == u["page"]
        close_y = abs(u["y"] - buffer["y"]) < y_gap

        no_end = not buffer["text"].strip().endswith((';', '.'))

        if same_page and close_y and no_end:
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
    """<u>...</u> 블록에서 상품 추출"""
    goods = []
    underline_blocks = re.findall(r"<u>(.*?)</u>", tagged_text)

    for block in underline_blocks:
        parts = [p.strip() for p in re.split(r"[;]", block) if p.strip()]

        for part in parts:
            goods.append(f"<u>{part}</u>")

    return goods


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
            full_goods_parts = [
                p.strip()
                for p in re.split(r"[;.]", u.get("full_text", ""))
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

    ANCHOR_PATTERN = re.compile(
        r"Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground",
        re.IGNORECASE
    )

    PAGE_NUM_PATTERN = re.compile(r'^\s*-\s*\d+\s*-\s*$')

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

                for match in reversed(matches):
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

    def flush_buffer():
        nonlocal buffer_texts, buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts, buffer_class

        if not buffer_texts:
            return

        full_text = " ".join(buffer_texts)
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        if full_text:
            tagged_text = apply_underline_tags(full_text, buffer_underlined_texts)

            # [Class XX] 추출
            class_match = re.search(r'\[Class\s+(\d+)\]', full_text, re.IGNORECASE)
            class_num = class_match.group(1) if class_match else buffer_class

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
        nonlocal buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts

        buffer_texts.append(text)
        buffer_page = page
        buffer_y0 = min(buffer_y0, y0)
        buffer_y1 = max(buffer_y1, y1)

        for ul in page_underlined_texts:
            if y0 - 5 <= ul["y"] <= y1 + 5:
                if ul not in buffer_underlined_texts:
                    buffer_underlined_texts.append(ul)

    after_anchor = False

    for page_num, page in enumerate(doc):
        text_dict = page.get_text("dict")
        page_underlined_texts = get_underlined_texts_for_page(page, page_num + 1)

        for block in text_dict["blocks"]:
            if "lines" not in block:
                continue

            for line_obj in block["lines"]:
                for span in line_obj["spans"]:
                    txt = span["text"]
                    bbox = span["bbox"]

                    if not txt.strip():
                        continue

                    if PAGE_NUM_PATTERN.match(txt.strip()):
                        continue

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

    flush_buffer()
    doc.close()
    return results


def match_goods_to_sections_comma(sections, tagged_results):
    """섹션에 상품 매칭 (comma 방식)"""
    final_results = []
    used_tagged = set()

    for section in sections:
        page_start = section["page_start"]
        page_end = section["page_end"]
        y_start = section["y_start"]
        y_end = section["y_end"]

        matched_list = []

        for idx, tr in enumerate(tagged_results):
            if idx in used_tagged:
                continue

            tr_page = tr["page"]
            tr_y0 = tr["y0"]

            if tr_page < page_start or tr_page > page_end:
                continue

            is_in_range = False

            if page_start == page_end:
                if y_start <= tr_y0 <= y_end:
                    is_in_range = True
            elif tr_page == page_start:
                if tr_y0 >= y_start:
                    is_in_range = True
            elif tr_page == page_end:
                if tr_y0 <= y_end:
                    is_in_range = True
            else:
                is_in_range = True

            if is_in_range:
                matched_list.append(tr)
                used_tagged.add(idx)

        final_results.append({
            "mark_number": section.get("mark_number"),
            "filing_number": section["filing_number"],
            "international_registration": section["international_registration"],
            "tagged_goods": matched_list
        })

    return final_results


# ============================================================
# 메인 처리 함수
# ============================================================

def process_pdf(pdf_path):
    """
    PDF 처리 메인 함수
    - 구분자 타입 자동 감지 (semicolon vs comma)
    - semicolon: 개별 상품 분리, 밑줄 있는 것만 추출
    - comma: 전체 문자열 유지, 밑줄 부분만 <u> 태그
    """
    delimiter_type = detect_delimiter_type(pdf_path)
    print(f"감지된 구분자 타입: {delimiter_type}")

    sections = extract_trademark_sections(pdf_path)

    if delimiter_type == 'semicolon':
        # ';' 기준: 개별 상품 분리
        underlines = extract_underlined_with_positions_semicolon(pdf_path)
        final_results = match_underlines_to_sections_semicolon(sections, underlines)

        return {
            "delimiter_type": delimiter_type,
            "sections": sections,
            "final_results": final_results
        }
    else:
        # ',' 기준: 전체 문자열 유지
        underlines = extract_underlines_only(pdf_path)
        tagged_results = extract_goods_with_spans_comma(pdf_path, underlines)
        final_results = match_goods_to_sections_comma(sections, tagged_results)

        return {
            "delimiter_type": delimiter_type,
            "sections": sections,
            "tagged_results": tagged_results,
            "final_results": final_results
        }


def print_results(data):
    """결과 출력"""
    delimiter_type = data.get('delimiter_type', 'unknown')

    print("\n" + "=" * 80)
    print(f"구분자 타입: {delimiter_type}")
    print("=" * 80 + "\n")

    if delimiter_type == 'semicolon':
        # ';' 기준: 개별 상품 목록
        for idx, r in enumerate(data['final_results'], 1):
            print(f"[{idx}] 상표 정보 (Earlier Mark {r.get('mark_number', '?')})")

            if r['filing_number']:
                print(f"    Filing Number: {r['filing_number']}")
            if r['international_registration']:
                print(f"    International Registration: {r['international_registration']}")

            goods_list = r.get('underlined_goods', [])
            print(f"    Underlined Goods: {len(goods_list)}개")

            if goods_list:
                print(f"\n    밑줄 친 상품 목록:")
                for i, goods_item in enumerate(goods_list, 1):
                    print(f"      {i}. {goods_item['goods']}")
            else:
                print(f"    (밑줄 없음)")

            print()
    else:
        # ',' 기준: 전체 문자열
        print("=" * 80)
        print("🔥 최종 결과 (전체 텍스트 + 밑줄 태그)")
        print("=" * 80 + "\n")

        for idx, r in enumerate(data['final_results'], 1):
            print(f"[{idx}] 상표 정보 (Earlier Mark {r.get('mark_number', '?')})")

            if r['filing_number']:
                print(f"    Filing Number: {r['filing_number']}")
            if r['international_registration']:
                print(f"    International Registration: {r['international_registration']}")

            tagged_goods = r.get('tagged_goods', [])
            if tagged_goods:
                print(f"\n    상품 목록 (밑줄 부분에 <u> 태그):")
                for i, goods_item in enumerate(tagged_goods, 1):
                    class_num = goods_item.get('class')
                    class_prefix = f"[Class {class_num}] " if class_num else ""
                    print(f"      {i}. {class_prefix}{goods_item['tagged_text']}")
            else:
                print(f"    (상품 없음)")

            print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = r"c:\Users\mark\Downloads\가거절 통지서\가거절 통지서\문제\552025075453328-02-복사.pdf"

    if not Path(pdf_path).exists():
        print(f"파일 없음: {pdf_path}")
        sys.exit(1)

    print("=" * 80)
    print(f"\n파일 분석 중: {pdf_path}\n")

    data = process_pdf(pdf_path)
    print_results(data)
