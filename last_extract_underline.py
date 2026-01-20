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
            if raw_text == '심사관\n파트장\n팀장\n국장\n':
                continue

            anchor_text = " ".join(raw_text.strip().split())

            if not anchor_text:
                continue

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
                remove_class=False
            )

            # ==================================================
            # 6️⃣ 제외 대상 검사
            # ==================================================
            if should_exclude_underlined_text(normalized_text):
                continue

            # underline 대상 텍스트에서 끝 구분자 제거
            m = re.match(r"^(.*?)([;.]?)$", normalized_text)
            underline_core = m.group(1)
            delimiter = m.group(2)

            if underline_core and underline_core in full_text:
                tagged_text = full_text.replace(
                    underline_core + delimiter,
                    f"<u>{underline_core}</u>{delimiter}",
                    1
                )
            else:
                tagged_text = f"<u>{underline_core}</u>{delimiter}"

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
        seen = set()
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
            goods = extract_goods_from_tagged_text(u["tagged_text"])
            for g in goods:
                if g not in seen:
                    seen.add(g)
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

    return results

def normalize_underlined_text(text: str, remove_class: bool = False) -> str:
    """
    밑줄 텍스트를 정규화하는 함수
    - 불필요한 prefix 제거
    - goods/services 형태 보정
    - Class 제거 옵션 처리
    """
    # 1️⃣ 앞뒤 공백 제거
    text = text.strip()

    # 2️⃣ 'all' 또는 'All' 단독인 경우 그대로 반환
    if re.fullmatch(r"(all|All)", text):
        return text

    # 3️⃣ '(underlined goods)' 제거
    before = text
    text = re.sub(
        r"^\(\s*underlined goods\s*\)\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # 4️⃣ '(underlined goods/services)' 제거
    before = text
    text = re.sub(
        r"^\(\s*underlined goods/services\s*\)\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # 5️⃣ Class 제거 옵션
    if remove_class:
        before = text
        text = remove_class_prefix(text)

    # 6️⃣ goods/services 로 끝나는 경우 ; 보정
    if re.search(r"goods/services\s*$", text, re.IGNORECASE):
        if not text.rstrip().endswith((';', '.')):
            text = text.rstrip() + ";"

    # 7️⃣ 최종 정리
    text = text.strip()

    return text

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
    규칙:
    1. ; 또는 . 기준으로 1차 분리
    2. <u>가 포함된 조각만 대상
    3. 연속된 <u> 조각은 하나의 상품으로 병합
    4. <u> 태그는 유지
    """
    goods = []

    # 1️⃣ 1차 분리
    parts = re.split(r'[;.]', tagged_text)

    buffer = None  # 병합용 버퍼

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "<u>" in part:
            if buffer is None:
                buffer = part
            else:
                # 🔥 delimiter 없이 연속 underline → 병합
                buffer = buffer.replace("</u>", "") + " " + part.replace("<u>", "")
        else:
            # underline 없는 조각을 만나면 버퍼 확정
            if buffer:
                goods.append(buffer.strip())
                buffer = None

    # 마지막 버퍼 처리
    if buffer:
        goods.append(buffer.strip())

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
                class_info = f"[Class {goods_item['class']}] " if goods_item['class'] else ""
                print(f"      {i}. {class_info}{goods_item['goods']}")
        else:
            print(f"    (밑줄 없음)")

        print()

def main(pdf_path):
    """메인 실행 함수"""
    print("=" * 80)
    print(f"\n파일 분석 중: {pdf_path}")

    sections = extract_trademark_sections(pdf_path)
    print(sections)
    underlines = extract_underlined_with_positions(pdf_path)
    print(underlines)
    results = match_underlines_to_sections(sections, underlines)

    print_results(results)

    return results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/문제/552025075457917-01-복사.pdf"

    if not Path(path).exists():
        print(f"파일 없음: {path}")
        sys.exit(1)

    main(path)