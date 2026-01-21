"""
통합 로직: ';'과 '.' 기준으로 데이터 분리 (','는 분리 기준 아님)
- last_extract_underline.py의 ';'과 '.' 분리 + 줄바꿈 병합 로직
- test_extract_underline.py의 부분 밑줄 처리 + <u> 태그 적용 로직
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

    # 'Information concerning the earlier mark' 시작점 찾기
    section_starts = []

    for idx, block in enumerate(all_blocks):
        text = block["text"]
        text_cleaned = text.replace("□", "").replace("☐", "").strip()

        # 패턴 1: 번호가 있는 경우 (1), (2) ...
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

        # 패턴 2: 번호 없는 경우 (단일 상표 문서)
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

    # 섹션 시작점이 없는 PDF 처리
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

    # 각 섹션의 범위 계산 + 정보 추출
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


def extract_goods_with_spans(pdf_path, underlines):
    """
    앵커 패턴 이후 텍스트를 ';'과 '.' 기준으로 분리하고
    밑줄 부분에만 <u> 태그 적용
    (','는 분리 기준이 아님 - 하나의 상품 내에서 사용됨)

    Args:
        pdf_path: PDF 파일 경로
        underlines: extract_underlines_only() 결과
    """
    doc = fitz.open(pdf_path)
    results = []

    # 앵커 패턴들
    ANCHOR_PATTERNS = [
        re.compile(
            r"Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground",
            re.IGNORECASE
        ),
        re.compile(
            r"\(\s*underlined\s+goods(?:/services)?\s*\)",
            re.IGNORECASE
        ),
    ]

    # 페이지 번호 패턴 (예: "- 5 -", "- 6 -")
    PAGE_NUM_PATTERN = re.compile(r'^\s*-\s*\d+\s*-\s*$')

    # 구분자: ';'과 '.'만 사용 (','는 분리 기준 아님)
    DELIMITER_REGEX = r'([;.])'
    DELIMITERS = [';', '.']

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
                # 제외 대상 체크
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

    # 버퍼: 텍스트 누적 (줄바꿈 처리용)
    buffer_texts = []
    buffer_page = None
    buffer_y0 = float('inf')
    buffer_y1 = 0
    buffer_underlined_texts = []

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

                    # 페이지 번호 스킵
                    if PAGE_NUM_PATTERN.match(txt.strip()):
                        continue

                    # 앵커 패턴 찾기
                    anchor_found = False
                    for pattern in ANCHOR_PATTERNS:
                        if pattern.search(txt):
                            anchor_found = True
                            break

                    if anchor_found:
                        after_anchor = True
                        # ":" 이후 텍스트 처리
                        colon_idx = txt.find(":")
                        if colon_idx != -1 and colon_idx < len(txt) - 1:
                            after_colon = txt[colon_idx + 1:].strip()
                            if after_colon:
                                # ';' 또는 '.'로 분리
                                parts = re.split(DELIMITER_REGEX, after_colon)
                                for part in parts:
                                    if not part:
                                        continue
                                    if part in DELIMITERS:
                                        flush_buffer()
                                        if part == '.':
                                            after_anchor = False
                                    else:
                                        add_to_buffer(part, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
                        continue

                    if not after_anchor:
                        continue

                    # 앵커 이후 텍스트 처리: ';'과 '.'로만 분리
                    if ';' in txt or '.' in txt:
                        parts = re.split(DELIMITER_REGEX, txt)
                        for part in parts:
                            if not part:
                                continue
                            if part in DELIMITERS:
                                flush_buffer()
                                if part == '.':
                                    after_anchor = False
                            else:
                                add_to_buffer(part, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
                    else:
                        # ','가 있어도 분리하지 않고 그대로 버퍼에 추가
                        add_to_buffer(txt, bbox[1], bbox[3], page_num + 1, page_underlined_texts)

    # 마지막 버퍼 처리
    flush_buffer()

    doc.close()
    return results


def should_exclude_underlined_text(text: str) -> bool:
    """
    밑줄 텍스트가 '상품 정보가 아닌 경우' 제외하기 위한 판단 함수
    """

    stripped = text.strip()

    # 1. << ... >> 형태 (메타/주석)
    if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
        return True

    # 2. 연락처 관련 키워드 포함 여부
    if re.search(r"\b(Fax|Tel\.?|Telephone|E-mail|Email)\b", stripped, re.IGNORECASE):
        return True

    # 3. 이메일 주소 포함
    if "@" in stripped:
        return True

    # 4. 심사관 직책 단독 텍스트
    if stripped in ["심사관 파트장 팀장 국장", "심사관 팀장 국장"]:
        return True

    # 5. 심사관 등 직책으로 시작하는 텍스트
    if stripped.startswith(('심사관', '파트장', '팀장', '국장')):
        return True

    # 6. underlined goods 메타 텍스트
    if re.search(r"underlined goods", stripped, re.IGNORECASE):
        return True

    return False


def find_all_matching_tagged(sec, tagged_list, used_indices):
    """섹션 범위 내에 있는 모든 tagged_result 찾기"""
    page_start = sec["page_start"]
    page_end = sec["page_end"]
    y_start = sec["y_start"]
    y_end = sec["y_end"]

    matched = []

    for idx, tr in enumerate(tagged_list):
        if idx in used_indices:
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
            matched.append(tr)
            used_indices.add(idx)

    return matched


def clean_tagged_text(tagged_text):
    """태그된 텍스트 정리"""
    if not tagged_text:
        return tagged_text

    # applied-for mark 설명 제거
    tagged_text = re.sub(
        r"^\*?\s*Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground:\s*",
        "",
        tagged_text,
        flags=re.IGNORECASE
    )

    # (underlined goods) 제거
    tagged_text = re.sub(r"^\(\s*underlined goods(?:/services)?\s*\)\s*", "", tagged_text, flags=re.IGNORECASE)

    # [Class XX] 제거
    tagged_text = re.sub(
        r"\s*\[\s*Class\s*\d+\s*\]\s*",
        "",
        tagged_text,
        flags=re.IGNORECASE
    )

    # 공백 정리
    tagged_text = re.sub(r'<u>\s+', '<u>', tagged_text)
    tagged_text = re.sub(r'\s+</u>', '</u>', tagged_text)
    tagged_text = re.sub(r'\s{2,}', ' ', tagged_text)

    return tagged_text.strip()


def process_pdf(pdf_path):
    """
    PDF 처리 메인 함수
    - ';'과 '.' 기준으로 상품 분리 (','는 분리 기준 아님)
    - 밑줄 추출 및 <u> 태그 적용
    - 섹션 매칭
    """
    # 1. 밑줄 좌표 추출
    underlines = extract_underlines_only(pdf_path)

    # 2. 섹션 정보 추출
    sections = extract_trademark_sections(pdf_path)

    # 3. Goods 추출 + 밑줄 태그 (';'과 '.' 기준 분리)
    tagged_results = extract_goods_with_spans(pdf_path, underlines)

    # 4. 섹션에 매칭
    final_results = []
    used_tagged = set()

    for section in sections:
        matched_list = find_all_matching_tagged(section, tagged_results, used_tagged)

        # 태그된 텍스트 정리
        for matched in matched_list:
            matched["tagged_text"] = clean_tagged_text(matched["tagged_text"])

        final_results.append({
            "mark_number": section.get("mark_number"),
            "filing_number": section["filing_number"],
            "international_registration": section["international_registration"],
            "tagged_goods": matched_list
        })

    return {
        "sections": sections,
        "tagged_results": tagged_results,
        "final_results": final_results
    }


def print_results(data):
    """결과 출력"""
    print("\n" + "=" * 80)
    print("구분자: ';'과 '.' 기준 분리 (','는 분리 안함)")
    print("=" * 80 + "\n")

    print("📍 밑줄 매칭 결과 (<u> 태그 적용):")
    for idx, item in enumerate(data['tagged_results'], 1):
        has_underline = "<u>" in item["tagged_text"]
        mark = "✅" if has_underline else "  "
        print(f"  {idx}. {mark} page={item['page']}")
        text_preview = item['text'][:100] + "..." if len(item['text']) > 100 else item['text']
        tagged_preview = item['tagged_text'][:100] + "..." if len(item['tagged_text']) > 100 else item['tagged_text']
        print(f"      원본: {text_preview}")
        print(f"      태그: {tagged_preview}")
    print()

    print("=" * 80)
    print("🔥 최종 결과 (전체 텍스트 + 밑줄 태그)")
    print("=" * 80 + "\n")

    for idx, r in enumerate(data['final_results'], 1):
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
