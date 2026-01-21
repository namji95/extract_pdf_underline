"""
현재 가장 적합한 로직
2026.01.16 ; 특수기호가 존재할 경우 ; 기준으로 데이터 분리 | ,가 있는 경우 , 기준으로 데이터 분리 => ;가 우선
merge_by_semicolon, split_products
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

    # PDF 열기
    doc = fitz.open(pdf_path)

    # 최종 섹션 결과
    sections = []

    # ==================================================
    # 1️⃣ 모든 페이지에서 텍스트 블록 수집
    # ==================================================
    all_blocks = []

    for page_num, page in enumerate(doc):

        # PyMuPDF dict 형태로 텍스트 추출
        blocks = page.get_text("dict")["blocks"]

        for block_idx, block in enumerate(blocks):
            # 텍스트 라인이 있는 블록만 사용
            if "lines" not in block:
                continue

            block_text = ""

            # 한 블록 안의 모든 span 텍스트를 하나로 합침
            for line in block["lines"]:
                for span in line["spans"]:
                    block_text += span["text"] + " "

            block_text = block_text.strip()

            block_info = {
                "page": page_num + 1,               # 페이지 번호
                "y0": block["bbox"][1],             # 블록 시작 y좌표
                "y1": block["bbox"][3],             # 블록 끝 y좌표
                "text": block_text                  # 블록 전체 텍스트
            }

            all_blocks.append(block_info)

    # ==================================================
    # 2️⃣ 'Information concerning the earlier mark' 시작점 찾기
    # ==================================================
    section_starts = []

    for idx, block in enumerate(all_blocks):
        text = block["text"]

        # PDF 체크박스 기호 제거
        text_cleaned = text.replace("□", "").replace("☐", "").strip()

        # 패턴 1️⃣ 번호가 있는 경우: (1), (2) ...
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

        # 패턴 2️⃣ 번호 없는 경우 (단일 상표 문서)
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

    # ==================================================
    # 3️⃣ 섹션 시작점이 아예 없는 PDF 처리
    # ==================================================
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

    # ==================================================
    # 4️⃣ 각 섹션의 범위 계산 + 정보 추출
    # ==================================================
    for i, start in enumerate(section_starts):

        # 다음 섹션이 있으면 거기 전까지
        if i + 1 < len(section_starts):
            end_idx = section_starts[i + 1]["index"]
            end_page = section_starts[i + 1]["page"]
            end_y = section_starts[i + 1]["y"]
        else:
            end_idx = len(all_blocks)
            end_page = all_blocks[-1]["page"]
            end_y = all_blocks[-1]["y1"]

        # 해당 섹션 텍스트 전체 합치기
        section_text = " ".join(
            all_blocks[j]["text"] for j in range(start["index"], end_idx)
        )

        # Filing number 추출
        filing_match = re.search(r"Filing\s+number\s*:\s*(\d+)", section_text)
        filing_number = filing_match.group(1) if filing_match else None

        # International registration number 추출
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

def extract_goods_with_spans(pdf_path, underlines):
    """
    "* Goods/Services of the applied-for mark in relation to this ground:" 이후
    텍스트를 ';' 또는 '.' 기준으로 분리하고, 밑줄이 있는 부분에만 <u> 태그 적용

    Args:
        pdf_path: PDF 파일 경로
        underlines: extract_underlines_only() 결과

    Returns:
        list of dict: [
            {
                "page": 페이지 번호,
                "text": 원본 텍스트 (상품 단위),
                "tagged_text": <u> 태그 적용된 텍스트,
                "y0": 시작 y좌표,
                "y1": 끝 y좌표,
            },
            ...
        ]
    """
    doc = fitz.open(pdf_path)
    results = []

    # 앵커 패턴
    ANCHOR_PATTERN = re.compile(
        r"Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground",
        re.IGNORECASE
    )

    # 페이지 번호 패턴 (예: "- 5 -", "- 6 -")
    PAGE_NUM_PATTERN = re.compile(r'^\s*-\s*\d+\s*-\s*$')

    def get_underlined_texts_for_page(page, page_num):
        """페이지에서 밑줄 바로 위의 텍스트 추출"""
        underlined_texts = []
        page_underlines = [ul for ul in underlines if ul["page"] == page_num]

        for ul in page_underlines:
            # 밑줄 바로 위 영역 (텍스트 높이 약 12pt)
            clip_rect = fitz.Rect(
                ul["x0"] - 1,
                ul["y"] - 12,
                ul["x1"] + 1,
                ul["y"] + 1
            )
            text = page.get_text("text", clip=clip_rect).strip()
            text = " ".join(text.split())  # 공백 정리

            if text:
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

        # 밑줄 텍스트들을 길이순 정렬 (긴 것 먼저 - 부분 매칭 방지)
        sorted_ul_texts = sorted(underlined_texts, key=lambda x: len(x["text"]), reverse=True)

        for ul in sorted_ul_texts:
            ul_text = ul["text"]
            if not ul_text:
                continue

            # 이미 태그된 부분 건너뛰기
            if f"<u>{ul_text}</u>" in tagged_text:
                continue

            # 정확한 텍스트 매칭 후 태그 적용
            if ul_text in tagged_text:
                # 이미 <u> 태그 안에 있는지 확인
                pattern = re.compile(re.escape(ul_text))
                matches = list(pattern.finditer(tagged_text))

                for match in reversed(matches):  # 뒤에서부터 처리
                    start, end = match.start(), match.end()

                    # 이미 <u> 태그 안에 있는지 확인
                    before = tagged_text[:start]
                    if before.count("<u>") > before.count("</u>"):
                        continue  # 이미 태그 안에 있음

                    tagged_text = tagged_text[:start] + f"<u>{ul_text}</u>" + tagged_text[end:]
                    break  # 첫 번째 매칭만 처리

        return tagged_text

    # 버퍼: 텍스트 누적
    buffer_texts = []  # [text, ...]
    buffer_page = None
    buffer_y0 = float('inf')
    buffer_y1 = 0
    buffer_underlined_texts = []  # 해당 버퍼 범위 내 밑줄 텍스트들

    def flush_buffer():
        """버퍼에 있는 텍스트를 합쳐서 results에 추가"""
        nonlocal buffer_texts, buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts

        if not buffer_texts:
            return

        # 텍스트 합치기
        full_text = " ".join(buffer_texts)
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        if full_text:
            # 밑줄 태그 적용
            tagged_text = apply_underline_tags(full_text, buffer_underlined_texts)

            results.append({
                "page": buffer_page,
                "text": full_text,
                "tagged_text": tagged_text,
                "y0": buffer_y0,
                "y1": buffer_y1,
            })

        # 초기화
        buffer_texts = []
        buffer_y0 = float('inf')
        buffer_y1 = 0
        buffer_underlined_texts = []

    def add_to_buffer(text, y0, y1, page, page_underlined_texts):
        """텍스트를 버퍼에 추가"""
        nonlocal buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts

        buffer_texts.append(text)
        buffer_page = page
        buffer_y0 = min(buffer_y0, y0)
        buffer_y1 = max(buffer_y1, y1)

        # 해당 y 범위에 있는 밑줄 텍스트 수집
        for ul in page_underlined_texts:
            if y0 - 5 <= ul["y"] <= y1 + 5:
                if ul not in buffer_underlined_texts:
                    buffer_underlined_texts.append(ul)

    after_anchor = False  # 페이지 간 상태 유지

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

                    # 페이지 번호 스킵
                    if PAGE_NUM_PATTERN.match(txt.strip()):
                        continue

                    # 앵커 찾기
                    if ANCHOR_PATTERN.search(txt):
                        after_anchor = True
                        # ":" 이후 텍스트 처리
                        colon_idx = txt.find(":")
                        if colon_idx != -1 and colon_idx < len(txt) - 1:
                            after_colon = txt[colon_idx + 1:].strip()
                            if after_colon:
                                # ';' 또는 '.'로 분리
                                parts = re.split(r'([;.])', after_colon)
                                for part in parts:
                                    if not part:
                                        continue
                                    if part in [';', '.']:
                                        flush_buffer()
                                        if part == '.':
                                            after_anchor = False
                                    else:
                                        add_to_buffer(part, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
                        continue

                    if not after_anchor:
                        continue

                    # 앵커 이후 텍스트 처리
                    if ';' in txt or '.' in txt:
                        parts = re.split(r'([;.])', txt)
                        for part in parts:
                            if not part:
                                continue
                            if part in [';', '.']:
                                flush_buffer()
                                if part == '.':
                                    after_anchor = False
                            else:
                                add_to_buffer(part, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
                    else:
                        add_to_buffer(txt, bbox[1], bbox[3], page_num + 1, page_underlined_texts)

    # 마지막 버퍼 처리
    flush_buffer()

    doc.close()
    return results

def extract_underlines_only(pdf_path):
    """
    PDF에서 밑줄(수평선)만 추출 (좌표 정보만)
    """
    doc = fitz.open(pdf_path)
    underlines = []

    for page_num, page in enumerate(doc):
        drawings = page.get_drawings()

        for d in drawings:
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]

                    # 수평선 판별
                    if abs(p1.y - p2.y) < 2:
                        length = abs(p2.x - p1.x)

                        # underline 후보 길이 제한
                        if 10 < length < 500:
                            underlines.append({
                                "page": page_num + 1,
                                "y": p1.y,
                                "x0": min(p1.x, p2.x),
                                "x1": max(p1.x, p2.x),
                            })

    doc.close()
    return underlines

def tag_goods_with_underlines(goods_lines, underlines, y_tolerance=5, x_tolerance=5):
    """
    goods_lines의 텍스트와 underlines의 좌표를 비교해서
    밑줄이 있는 부분에 <u> 태그를 적용

    Args:
        goods_lines: extract_goods_lines_with_positions() 결과
        underlines: extract_underlines_only() 결과
        y_tolerance: y좌표 허용 오차
        x_tolerance: x좌표 허용 오차

    Returns:
        list of dict: [
            {
                "page": 페이지,
                "text": 원본 텍스트,
                "tagged_text": <u> 태그 적용된 텍스트,
                "has_underline": 밑줄 여부,
                "matched_underlines": 매칭된 밑줄 목록,
            },
            ...
        ]
    """
    results = []

    for goods in goods_lines:
        page = goods["page"]
        text = goods["text"]
        g_x0 = goods["x0"]
        g_x1 = goods["x1"]
        g_y0 = goods["y0"]
        g_y1 = goods["y1"]

        # 해당 goods_line과 매칭되는 모든 밑줄 찾기
        matched_underlines = []

        for ul in underlines:
            # 같은 페이지인지
            if ul["page"] != page:
                continue

            ul_y = ul["y"]
            ul_x0 = ul["x0"]
            ul_x1 = ul["x1"]

            # y좌표 비교: 밑줄이 텍스트 y0~y1 범위 안에 있는지
            # (텍스트가 여러 줄에 걸쳐있으므로 범위 안에 있으면 매칭)
            if not (g_y0 - y_tolerance <= ul_y <= g_y1 + y_tolerance):
                continue

            # x좌표 비교: 밑줄이 텍스트 범위와 겹치는지
            x_overlap = max(0, min(g_x1, ul_x1) - max(g_x0, ul_x0))
            if x_overlap < x_tolerance:
                continue

            matched_underlines.append(ul)

        if matched_underlines:
            # 전체 텍스트에 <u> 태그 적용
            tagged_text = f"<u>{text}</u>"
            has_underline = True
        else:
            tagged_text = text
            has_underline = False

        results.append({
            "page": page,
            "text": text,
            "tagged_text": tagged_text,
            "has_underline": has_underline,
            "matched_underlines": matched_underlines,
            "y0": g_y0,
            "y1": g_y1,
        })

    return results

def extract_underlined_with_positions(pdf_path):
    """
    PDF에서 '밑줄(underline)'에 해당하는 수평선을 직접 탐지하고,
    해당 수평선 바로 위에 위치한 텍스트를 추출한 뒤
    같은 줄의 전체 텍스트에서 밑줄 부분을 <u> 태그로 감싼다.

    ✔ underline style 미사용
    ✔ 실제 draw된 수평선(line) 기준
    ✔ underline = anchor
    ✔ <u>는 full line 기준 적용
    """

    # ==================================================
    # 0️⃣ PDF 파일 오픈
    # ==================================================
    doc = fitz.open(pdf_path)
    results = []

    # ==================================================
    # 1️⃣ 페이지 단위 순회
    # ==================================================
    for page_num, page in enumerate(doc):
        text_dict = page.get_text("dict")

        spans_after_applied_for = []
        after_anchor = False

        for block in text_dict["blocks"]:
            if "lines" not in block:
                continue

            for line_obj in block["lines"]:
                for span in line_obj["spans"]:
                    txt = span["text"].strip()
                    if not txt:
                        continue

                    # 기준 anchor
                    if re.search(
                            r"Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground",
                            txt,
                            re.IGNORECASE
                    ):
                        after_anchor = True
                        continue

                    if not after_anchor:
                        continue

                    spans_after_applied_for.append({
                        "text": txt,
                        "bbox": span["bbox"]  # (x0, y0, x1, y1)
                    })

        drawings = page.get_drawings()
        lines = []

        # ==================================================
        # 2️⃣ 수평선(underline) 탐색
        # ==================================================
        for d in drawings:
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]

                    # 수평선 판별
                    if abs(p1.y - p2.y) < 2:
                        length = abs(p2.x - p1.x)

                        # underline 후보 길이 제한
                        if 10 < length < 500:
                            lines.append({
                                "y": p1.y,
                                "x0": min(p1.x, p2.x),
                                "x1": max(p1.x, p2.x),
                            })

        # ==================================================
        # 3️⃣ 각 밑줄 기준 텍스트 추출
        # ==================================================
        for idx, line in enumerate(lines):

            # ------------------------------------------
            # (1) 밑줄 바로 위 영역 (anchor text)
            # ------------------------------------------
            anchor_rect = fitz.Rect(
                line["x0"] - 1,
                line["y"] - 12,
                line["x1"] + 1,
                line["y"] + 1,
            )

            raw_text = page.get_text("text", clip=anchor_rect)
            if (
                    raw_text.startswith('심사관') or
                    raw_text.startswith('파트장') or
                    raw_text.startswith('팀장') or
                    raw_text.startswith('국장')
            ):
                continue

            anchor_text = " ".join(raw_text.strip().split())

            if not anchor_text:
                continue

            # TODO: 여기를 활용해서 풀텍스트 가져오는 테스트 해볼 것
            # ------------------------------------------
            # (2) 같은 줄 전체 텍스트 (page width)
            # ------------------------------------------
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

            # ======================================================

            full_rect_test = fitz.Rect(
                0,
                line["y"] - 12,
                page.rect.width,
                line["y"] + 35,
            )

            full_raw_text_test = page.get_text("text", clip=full_rect_test)
            full_text_test = " ".join(full_raw_text_test.strip().split())
            print(full_text_test)

            full_text_test = normalize_underlined_text(
                full_text_test,
                remove_class=True
            )

            if should_exclude_underlined_text(full_text_test):
                continue

            if not full_text_test:
                continue

            # print(f"{anchor_text} | {full_text_test}")

            # ======================================================

            # ==================================================
            # 4️⃣ Class 정보 추출
            # ==================================================
            match = re.search(r'\[Class\s+(\d+)\]', full_text, re.IGNORECASE)
            class_num = match.group(1) if match else None

            # ==================================================
            # 5️⃣ 밑줄 텍스트 정규화
            # ==================================================
            normalized_text = normalize_underlined_text(
                anchor_text,
                remove_class=True
            )

            # ==================================================
            # 6️⃣ 제외 대상 검사
            # ==================================================
            if should_exclude_underlined_text(normalized_text):
                continue

            # ==================================================
            # 7️⃣ <u> 태그 적용 (상품 단위 기준, 1 underline = 1 결과)
            # ==================================================

            # underline_core (delimiter 제거)
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

                # 1️⃣ 정확히 일치
                if compare_part == compare_underline:
                    tagged_text = f"<u>{compare_part}</u>"
                    break

            # fallback (anchor만 있는 경우)
            if not tagged_text:
                tagged_text = f"<u>{underline_core}</u>"

            # ==================================================
            # 8️⃣ 결과 저장
            # ==================================================
            result_item = {
                "page": page_num + 1,
                "y": line["y"],
                "text": normalized_text,   # underline text
                "full_text": full_text,    # 전체 라인
                "tagged_text": tagged_text,  # <u> 적용
                "class": class_num,
            }

            results.append(result_item)

    # ==================================================
    # 9️⃣ PDF 닫기
    # ==================================================
    doc.close()
    return results

def match_underlines_to_sections(sections, underlines):
    results = []

    for section in sections:
        goods_list = []

        # 1️⃣ 섹션에 속하는 underline 먼저 수집
        section_underlines = []
        for u in underlines:
            if not (section["page_start"] <= u["page"] <= section["page_end"]):
                continue
            if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
                continue
            if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
                continue

            section_underlines.append(u)

        # 2️⃣ 🔥 여기서 underline 병합
        section_underlines = merge_multiline_underlines(section_underlines)

        # 3️⃣ 이제 안전하게 tagged_text 파싱
        for u in section_underlines:
            ALL_DESIGNATED_PATTERN = re.compile(
                r'(?i)[\'\"""]?\s*all\s*[\'\"""]?\s+the\s+designated\s+(goods\s*/\s*services|goods|services)',
                re.VERBOSE
            )
            # 🔥 1️⃣ ALL 지정 케이스 선처리
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
                # cosmetics → cosmetics for animals
                # full_text에 core가 '단독 상품'으로 존재하는지 체크
                standalone_exists = any(
                    p.strip().lower() == core.lower()
                    for p in full_goods_parts
                )

                for part in full_goods_parts:
                    # cosmetics → cosmetics for animals (허용)
                    if (
                            part.lower().startswith(core.lower() + " ")
                            and not standalone_exists  # 🔥 핵심 조건
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

def normalize_underlined_text(text: str, remove_class: bool = False) -> str:
    text = text.strip()

    # ✅ applied-for mark 메타 prefix 제거 (강화 버전)
    text = re.sub(
        r"^\s*(?:\[\s*Class\s*\d+\s*\]\s*)?\*?\s*Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground:\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # 'all' 단독
    if re.fullmatch(r"(all|All)", text):
        return text

    # (underlined goods) 제거
    text = re.sub(r"^\(\s*underlined goods\s*\)\s*", "", text, flags=re.I)
    text = re.sub(r"^\(\s*underlined goods/services\s*\)\s*", "", text, flags=re.I)

    if remove_class:
        text = remove_class_prefix(text)

    return text.strip()

def should_exclude_underlined_text(text: str) -> bool:
    """
    밑줄 텍스트가 '상품 정보가 아닌 경우' 제외하기 위한 판단 함수
    """

    stripped = text.strip()

    # 1️⃣ << ... >> 형태 (메타/주석)
    if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
        return True

    # 2️⃣ 연락처 관련 키워드 포함 여부
    if re.search(r"\b(Fax|Tel\.?|Telephone|E-mail|Email)\b", stripped, re.IGNORECASE):
        return True

    # 3️⃣ 이메일 주소 포함
    if "@" in stripped:
        return True

    # 4️⃣ 심사관 직책 단독 텍스트
    if stripped in ["심사관 파트장 팀장 국장", "심사관 팀장 국장"]:
        return True

    if re.search(r"(underlined goods)|underlined goods", stripped):
        return True

    return False

def merge_multiline_underlines(underlines, y_gap=20):
    """
    줄바꿈된 underline을 하나의 상품으로 병합
    """
    underlines = sorted(underlines, key=lambda x: (x["page"], x["y"]))
    merged = []

    buffer = None

    for u in underlines:
        if buffer is None:
            buffer = u.copy()
            continue

        same_page = buffer["page"] == u["page"]
        close_y = abs(u["y"] - buffer["y"]) < y_gap

        # 🔥 이전 underline이 문장 종료가 아니면 병합
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

def extract_goods_from_tagged_text(tagged_text: str) -> list[str]:
    """
    최소 수정 버전
    - <u>...</u> 내부에 여러 상품이 있으면 ; 기준으로 분리
    - 결과는 항상 '상품 1개 = <u>1개</u>'
    """

    goods = []

    # <u>...</u> 블록 단위 추출
    underline_blocks = re.findall(r"<u>(.*?)</u>", tagged_text)

    for block in underline_blocks:
        # ; 우선 분리
        parts = [p.strip() for p in re.split(r"[;]", block) if p.strip()]

        for part in parts:
            goods.append(f"<u>{part}</u>")

    return goods

def remove_class_prefix(text: str) -> str:
    """
    텍스트 앞에 붙은 [Class XX] 패턴을 제거하는 함수
    예:
      "[Class 10] Shampoos" → "Shampoos"
    """

    cleaned = re.sub(
        r'\[Class\s+\d+\]\s*',  # [Class 10] 패턴
        '',
        text,
        flags=re.IGNORECASE
    ).strip()

    return cleaned

def clean_goods_text(goods: str) -> str:
    """
    최종 결과용 goods 문자열 정리
    - applied-for mark 설명 제거
    - [Class XX] 제거 (위치 무관, <u> 밖/안 모두)
    - <u> 태그는 유지
    """

    if not goods:
        return goods

    # 1️⃣ applied-for mark 설명 제거
    goods = re.sub(
        r"^\*\s*Goods/Services of the applied-for mark in relation to this ground:\s*",
        "",
        goods,
        flags=re.IGNORECASE
    )

    # 2️⃣ [Class XX] 제거 (앞/중간/뒤, 공백 포함 전부)
    goods = re.sub(
        r"\s*\[\s*Class\s*\d+\s*\]\s*",
        "",
        goods,
        flags=re.IGNORECASE
    )

    # 3️⃣ <u> 바로 뒤에 생긴 공백 정리
    goods = re.sub(r"<u>\s+", "<u>", goods)

    # 4️⃣ 다중 공백 정리
    goods = re.sub(r"\s{2,}", " ", goods)

    return goods.strip()

def normalize_for_compare(text: str) -> str:
    """
    상품 비교용 정규화
    - applied-for mark 설명 제거
    - [Class XX] 제거
    - 공백 정리
    """
    if not text:
        return ""

    # applied-for mark 설명 제거
    text = re.sub(
        r"^\*\s*Goods/Services of the applied-for mark in relation to this ground:\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # applied-for mark 설명 제거
    text = re.sub(
        r"^\*\s* Goods of the proposed mark refused by this ground for refusal :\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # applied-for mark 설명 제거
    text = re.sub(
        r"^\*\s* Goods of the proposed mark refused under this ground :\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # [Class XX] 제거
    text = re.sub(
        r"\[\s*Class\s*\d+\s*\]",
        "",
        text,
        flags=re.IGNORECASE
    )

    # 공백 정리
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


def print_results(results):
    """결과를 보기 좋게 출력"""

    print("\n" + "=" * 80)
    print("상표별 밑줄 상품 분석 결과")
    print("=" * 80 + "\n")

    for idx, r in enumerate(results, 1):
        print(f"[{idx}] 상표 정보 (Earlier Mark {r.get('mark_number', '?')})")

        if r['filing_number']:
            print(f"    Filing Number: {r['filing_number']}")
        if r['international_registration']:
            print(f"    International Registration: {r['international_registration']}")

        print(f"    Underlined Goods: {len(r['underlined_goods'])}개")

        if r['underlined_goods']:
            print(f"\n    밑줄 친 상품 목록:")
            for i, goods_item in enumerate(r['underlined_goods'], 1):
                print(f"      {i}. {goods_item['goods']}")
        else:
            print(f"    (밑줄 없음)")

        print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/문제/552025075457917-01-복사.pdf"

    if not Path(pdf_path).exists():
        print(f"파일 없음: {pdf_path}")
        sys.exit(1)

    print("=" * 80)
    print(f"\n파일 분석 중: {pdf_path}\n")

    # ==================================================
    # 1️⃣ 밑줄(수평선) 좌표만 추출
    # ==================================================
    underlines_only = extract_underlines_only(pdf_path)
    print("\n📍 밑줄(수평선) 좌표:")
    for idx, ul in enumerate(underlines_only, 1):
        print(f"  {idx}. page={ul['page']}, y={ul['y']:.1f}, x0={ul['x0']:.1f}, x1={ul['x1']:.1f}")
    print()

    # ==================================================
    # 2️⃣ 🔥 Goods/Services 추출 + 밑줄 부분만 <u> 태그 적용
    # ==================================================
    tagged_results = extract_goods_with_spans(pdf_path, underlines_only)
    print("\n📍 밑줄 매칭 결과 (<u> 태그 적용):")
    for idx, item in enumerate(tagged_results, 1):
        has_underline = "<u>" in item["tagged_text"]
        underline_mark = "✅" if has_underline else "  "
        print(f"  {idx}. {underline_mark} page={item['page']}")
        print(f"      원본: {item['text']}")
        print(f"      태그: {item['tagged_text']}")
    print()

    # ==================================================
    # 3️⃣ 섹션 정보 추출
    # ==================================================
    sections = extract_trademark_sections(pdf_path)

    # ==================================================
    # 4️⃣ 🔥 tagged_results를 sections에 매칭 (페이지 범위 기반)
    # ==================================================
    def find_matching_tagged(sec, tagged_list):
        """섹션 범위 내에 있는 tagged_result 찾기"""
        page_start = sec["page_start"]
        page_end = sec["page_end"]
        y_start = sec["y_start"]
        y_end = sec["y_end"]

        for tr in tagged_list:
            tr_page = tr["page"]
            tr_y0 = tr["y0"]

            # 페이지 범위 체크
            if tr_page < page_start or tr_page > page_end:
                continue

            # 단일 페이지 섹션
            if page_start == page_end:
                if y_start <= tr_y0 <= y_end:
                    return tr
                continue

            # 여러 페이지에 걸친 섹션
            if tr_page == page_start:
                # 시작 페이지: y_start 이후
                if tr_y0 >= y_start:
                    return tr
            elif tr_page == page_end:
                # 끝 페이지: y_end 이전
                if tr_y0 <= y_end:
                    return tr
            else:
                # 중간 페이지
                return tr

        return None

    final_results = []
    used_tagged = set()  # 이미 매칭된 tagged_result 추적

    for section in sections:
        matched = find_matching_tagged(section, tagged_results)

        matched_tagged = []
        if matched:
            # 중복 사용 체크
            tr_key = (matched["page"], matched["y0"])
            if tr_key not in used_tagged:
                matched_tagged.append(matched)
                used_tagged.add(tr_key)

        final_results.append({
            "mark_number": section.get("mark_number"),
            "filing_number": section["filing_number"],
            "international_registration": section["international_registration"],
            "tagged_goods": matched_tagged
        })

    # ==================================================
    # 5️⃣ 최종 결과 출력
    # ==================================================
    print("\n" + "=" * 80)
    print("🔥 최종 결과 (전체 텍스트 + 밑줄 태그)")
    print("=" * 80 + "\n")

    for idx, r in enumerate(final_results, 1):
        print(f"[{idx}] 상표 정보 (Earlier Mark {r.get('mark_number', '?')})")

        if r['filing_number']:
            print(f"    Filing Number: {r['filing_number']}")
        if r['international_registration']:
            print(f"    International Registration: {r['international_registration']}")

        if r['tagged_goods']:
            print(f"\n    상품 목록 (밑줄 부분에 <u> 태그):")
            for i, goods_item in enumerate(r['tagged_goods'], 1):
                print(f"      {i}. {goods_item['tagged_text']}")
        else:
            print(f"    (상품 없음)")

        print()