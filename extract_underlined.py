# # 아래 로직은 밑줄 데이터만 추출
# # """
# # PDF에서 밑줄 친 텍스트를 추출하는 스크립트
# #
# # 핵심 아이디어:
# # - PDF는 '밑줄'을 스타일 정보로 저장하지 않는 경우가 많다
# # - 대신 '수평선(line drawing)' 객체로 저장된 경우가 많다
# # - 이 수평선 바로 위에 있는 텍스트를 밑줄 텍스트로 간주한다
# #
# # 필요 라이브러리:
# # pip install pymupdf
# # """
# #
# # import re
# # import fitz           # PyMuPDF: PDF 내부 구조(텍스트, 도형, 선 등)를 다룰 수 있는 라이브러리
# # import sys            # 커맨드라인 인자 처리용
# # from pathlib import Path  # 파일 경로 존재 여부 확인용
# #
# #
# # def extract_underlined(pdf_path):
# #     """
# #     PDF에서 밑줄 텍스트를 추출하는 함수 (선 기반)
# #
# #     pdf_path: 분석할 PDF 파일 경로
# #     return: [
# #         { "page": 페이지번호, "text": 밑줄친 텍스트 },
# #         ...
# #     ]
# #     """
# #
# #     # PDF 파일 열기 (문서 객체 생성)
# #     doc = fitz.open(pdf_path)
# #
# #     # 최종 결과를 담을 리스트
# #     results = []
# #
# #     # 페이지 단위로 순회
# #     # page_num: 0부터 시작하는 페이지 인덱스
# #     # page: 실제 페이지 객체
# #     for page_num, page in enumerate(doc):
# #
# #         # --------------------------------------------------
# #         # 1️⃣ 이 페이지에 그려진 모든 도형(drawing) 가져오기
# #         # --------------------------------------------------
# #         # get_drawings():
# #         # - 선(line)
# #         # - 사각형(rect)
# #         # - 곡선(curve)
# #         # - 기타 그래픽 요소
# #         # 를 모두 포함한 리스트를 반환
# #         drawings = page.get_drawings()
# #
# #         # 이 페이지에서 발견된 "수평선"만 모아둘 리스트
# #         lines = []
# #
# #         # 각 drawing 객체 순회
# #         for d in drawings:
# #             # drawing 내부에는 실제 그래픽 명령들이 items로 들어 있음
# #             for item in d.get("items", []):
# #
# #                 # item 구조 예:
# #                 # ("l", Point(x1,y1), Point(x2,y2)) → 선(line)
# #                 # 첫 번째 값 item[0] == "l" 이면 선
# #                 if item[0] == "l":
# #                     p1, p2 = item[1], item[2]  # 선의 시작점, 끝점
# #
# #                     # --------------------------------------------------
# #                     # 수평선 판별
# #                     # --------------------------------------------------
# #                     # y 좌표 차이가 거의 없으면 수평선으로 간주
# #                     # (PDF 좌표계에서는 소수점 오차가 있으므로 < 2 정도 허용)
# #                     if abs(p1.y - p2.y) < 2:
# #
# #                         # 선의 길이 계산 (x축 방향)
# #                         length = abs(p2.x - p1.x)
# #
# #                         # --------------------------------------------------
# #                         # 너무 짧거나 너무 긴 선은 제외
# #                         # - 10px 미만: 글자 밑줄이 아닐 가능성
# #                         # - 500px 초과: 표, 구분선일 가능성
# #                         # --------------------------------------------------
# #                         if 10 < length < 500:
# #                             lines.append({
# #                                 # 선의 y 좌표 (밑줄 위치)
# #                                 "y": p1.y,
# #
# #                                 # 선의 시작 x
# #                                 "x0": min(p1.x, p2.x),
# #
# #                                 # 선의 끝 x
# #                                 "x1": max(p1.x, p2.x)
# #                             })
# #
# #         # --------------------------------------------------
# #         # 2️⃣ 각 수평선 바로 위에 있는 텍스트 추출
# #         # --------------------------------------------------
# #         for line in lines:
# #             # 텍스트를 추출할 영역(Rect) 정의
# #             #
# #             # 왜 이렇게 잡나?
# #             # - 밑줄은 보통 텍스트 바로 "아래"에 있음
# #             # - 그래서 선 기준으로 위쪽(y-12) 영역을 잘라서 텍스트를 읽음
# #             rect = fitz.Rect(
# #                 line["x0"] - 1,     # 좌측 여유
# #                 line["y"] - 12,     # 선 위쪽 영역
# #                 line["x1"] + 1,     # 우측 여유
# #                 line["y"] + 1       # 선 바로 위까지
# #             )
# #
# #             # 해당 영역에서 텍스트 추출
# #             # "text" 옵션 → 순수 텍스트로 반환
# #             text = page.get_text("text", clip=rect).strip()
# #
# #             # 여러 줄/공백을 한 줄로 정리
# #             text = " ".join(text.split())
# #
# #             # ⭐ 설명용 prefix 제거
# #             text = normalize_underlined_text(text)
# #
# #             # 의미 없는 값 제외
# #             # - 빈 문자열
# #             # - 한 글자 이하
# #             if text and len(text) > 1 and not should_exclude_underlined_text(text):
# #                 results.append({
# #                     "page": page_num + 1, # 사람 기준 페이지 번호 (1부터)
# #                     "text": text
# #                 })
# #
# #     # PDF 닫기 (리소스 해제)
# #     doc.close()
# #
# #     return results
# #
# #
# # def normalize_underlined_text(text: str) -> str:
# #     """
# #     밑줄 텍스트에서
# #     - 상품과 무관한 설명용 prefix 제거
# #     - goods/services 로 끝나는 상품은 세미콜론 보정
# #     """
# #
# #     original = text
# #     text = text.strip()
# #
# #     # --------------------------------------------------
# #     # 1️⃣ (underlined goods/services) prefix 제거
# #     # --------------------------------------------------
# #     text = re.sub(
# #         r"^\(\s*underlined goods/services\s*\)\s*",
# #         "",
# #         text,
# #         flags=re.IGNORECASE
# #     )
# #
# #     # --------------------------------------------------
# #     # 2️⃣ goods/services 로 끝나는 경우 세미콜론 보정
# #     # --------------------------------------------------
# #     # 조건:
# #     # - prefix 제거 후 결과에 적용
# #     # - 이미 ; 또는 . 으로 끝나면 추가하지 않음
# #     # - 정확히 goods/services 로 "끝나는" 경우만
# #     if re.search(r"goods/services\s*$", text, re.IGNORECASE):
# #         if not text.rstrip().endswith((';', '.')):
# #             text = text.rstrip() + ";"
# #
# #     return text.strip()
# #
# #
# #
# # def should_exclude_underlined_text(text: str) -> bool:
# #     """
# #     밑줄 텍스트 중 '무조건 제거해야 하는 것'만 걸러낸다.
# #     상품 여부 판단은 하지 않는다.
# #     """
# #
# #     stripped = text.strip()
# #
# #     # 1️⃣ << ... >> 형태의 섹션/UI 헤더 제거
# #     if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
# #         return True
# #
# #     # 2️⃣ 이메일 / 연락처 라인 제거 (라인 시작 기준)
# #     if re.match(r"^(E-mail|Email|Telephone|Tel\.?|Fax)\s*:", stripped, re.IGNORECASE):
# #         return True
# #
# #     # 3️⃣ 이메일 주소가 포함된 단독 라인 제거
# #     if "@" in stripped:
# #         return True
# #
# #     # 4️⃣ 심사관 직함 라인 제거 (명시적 문자열 매칭)
# #     # 👉 여기서는 '판단'이 아니라 '지정 제거'
# #     if stripped == "심사관 파트장 팀장 국장":
# #         return True
# #
# #     return False
# #
# #
# # def merge_by_semicolon(results):
# #     """
# #     밑줄 추출 결과(results)를 세미콜론(;) 또는 마침표(.) 기준으로 병합한다.
# #
# #     results 입력 형태:
# #     [
# #         {"page": 2, "text": "provision of"},
# #         {"page": 2, "text": "space on web sites for advertising goods and services;"},
# #         {"page": 3, "text": "jewellery;"},
# #         ...
# #     ]
# #
# #     반환 형태:
# #     [
# #         {"page": 2, "text": "provision of space on web sites for advertising goods and services"},
# #         {"page": 3, "text": "jewellery"},
# #         ...
# #     ]
# #
# #     핵심 개념:
# #     - PDF에서는 한 상품명이 여러 줄로 끊어져 있을 수 있다
# #     - 세미콜론(;) 또는 마침표(.)는 '상품 하나의 종료'를 의미한다
# #     - 따라서 해당 기호가 나올 때까지 텍스트를 누적한다
# #     """
# #
# #     # 최종 병합 결과를 담을 리스트
# #     merged = []
# #
# #     # 현재 상품을 구성 중인 임시 버퍼
# #     # 여러 줄을 하나의 상품으로 합칠 때 사용
# #     current_text = ""
# #
# #     # 현재 버퍼에 담긴 텍스트가 속한 페이지 번호
# #     # 페이지 변경 시 버퍼를 강제로 확정하기 위해 필요
# #     current_page = None
# #
# #     # 추출된 밑줄 결과를 순서대로 순회
# #     # results는 PDF 상에서 읽은 순서를 유지해야 함
# #     for item in results:
# #
# #         # 현재 줄의 텍스트 (밑줄로 추출된 단위)
# #         text = item["text"]
# #
# #         # 해당 텍스트가 위치한 페이지 번호
# #         page = item["page"]
# #
# #         # --------------------------------------------------
# #         # 1️⃣ 페이지 변경 감지
# #         # --------------------------------------------------
# #         # 이전 줄과 현재 줄의 페이지가 다르면
# #         # → 이전 페이지에서 누적 중이던 상품을 강제로 확정
# #         if current_page is not None and page != current_page:
# #
# #             # 누적 중인 텍스트가 있다면 결과로 추가
# #             if current_text:
# #                 merged.append({
# #                     "page": current_page,
# #                     # ⭐ 마지막 특수기호 제거
# #                     "text": current_text.rstrip(";.").strip()
# #                 })
# #
# #                 # 버퍼 초기화
# #                 current_text = ""
# #
# #         # 현재 처리 중인 페이지 번호 갱신
# #         current_page = page
# #
# #         # --------------------------------------------------
# #         # 2️⃣ 텍스트 누적
# #         # --------------------------------------------------
# #         # 이미 누적 중인 텍스트가 있으면
# #         # → 공백을 하나 넣고 이어 붙임
# #         if current_text:
# #             current_text += " " + text
# #         else:
# #             # 누적 중인 텍스트가 없다면 새로 시작
# #             current_text = text
# #
# #         # --------------------------------------------------
# #         # 3️⃣ 상품 종료 조건 판단
# #         # --------------------------------------------------
# #         # 세미콜론(;) 또는 마침표(.)로 끝나면
# #         # → 하나의 상품이 완성되었다고 판단
# #         if current_text.endswith(";") or current_text.endswith("."):
# #
# #             # 완성된 상품을 결과 리스트에 추가
# #             merged.append({
# #                 "page": current_page,
# #                 # ⭐ 마지막 특수기호 제거
# #                 "text": current_text.rstrip(";.").strip()
# #             })
# #
# #             # 다음 상품을 위해 버퍼 초기화
# #             current_text = ""
# #
# #     # --------------------------------------------------
# #     # 4️⃣ 루프 종료 후 남은 텍스트 처리
# #     # --------------------------------------------------
# #     # 파일의 마지막 부분에서는
# #     # 세미콜론 없이 끝나는 상품이 있을 수 있음
# #     if current_text:
# #         merged.append({
# #             "page": current_page,
# #             # ⭐ 마지막 특수기호 제거
# #             "text": current_text.rstrip(";.").strip()
# #         })
# #
# #     # 병합된 최종 결과 반환
# #     return merged
# #
# #
# # def split_products(merged_results):
# #     """
# #     병합된 상품 텍스트에서 세미콜론(;) 기준으로
# #     개별 상품 단위로 분해하는 함수.
# #
# #     merged_results 입력 형태:
# #     [
# #         {"page": 11, "text": "Office furniture; desks; tea tables"},
# #         {"page": 11, "text": "book shelves rocking chairs"},
# #         ...
# #     ]
# #
# #     반환 형태:
# #     [
# #         {"page": 11, "text": "Office furniture"},
# #         {"page": 11, "text": "desks"},
# #         {"page": 11, "text": "tea tables"},
# #         {"page": 11, "text": "book shelves rocking chairs"},
# #         ...
# #     ]
# #
# #     핵심 개념:
# #     - merge_by_semicolon 단계에서는
# #       "줄 깨짐(line break)"만 해결한다.
# #     - 하지만 한 줄 안에 여러 상품이 들어 있는 경우가 많다.
# #     - 이 함수는 세미콜론(;)을
# #       "상품과 상품을 나누는 구분자"로 사용하여
# #       최종 상품 단위로 분해한다.
# #     """
# #
# #     # 최종적으로 반환할 결과 리스트
# #     # 각 요소는 {page, text} 형태의 단일 상품
# #     final_results = []
# #
# #     # 병합된 결과를 순서대로 순회
# #     # 이 순서는 PDF 원문에 나타난 순서를 그대로 유지함
# #     for item in merged_results:
# #
# #         # 해당 상품이 등장한 페이지 번호
# #         # (merge 단계에서 이미 확정된 값)
# #         page = item["page"]
# #
# #         # 병합된 상품 텍스트
# #         # 예: "Office furniture; desks; tea tables"
# #         text = item["text"]
# #
# #         # --------------------------------------------------
# #         # 1️⃣ 세미콜론 기준 분해
# #         # --------------------------------------------------
# #         # split(";"):
# #         #   "Office furniture; desks; tea tables"
# #         # → ["Office furniture", " desks", " tea tables"]
# #         #
# #         # strip():
# #         #   각 조각의 앞뒤 공백 제거
# #         #
# #         # if p.strip():
# #         #   빈 문자열 제거
# #         parts = [
# #             p.strip()
# #             for p in text.split(";")
# #             if p.strip()
# #         ]
# #
# #         # --------------------------------------------------
# #         # 2️⃣ 개별 상품 단위로 결과 생성
# #         # --------------------------------------------------
# #         # 하나의 merged item에서
# #         # 여러 개의 최종 상품이 만들어질 수 있음
# #         for part in parts:
# #             final_results.append({
# #                 "page": page,  # 원본 페이지 번호 유지
# #                 "text": part   # 최종 상품명 (세미콜론 제거됨)
# #             })
# #
# #     # 세미콜론 분해가 완료된 최종 상품 리스트 반환
# #     return final_results
# #
# #
# # def main(pdf_path):
# #     """
# #     스크립트 실행용 메인 함수
# #     """
# #
# #     print(f"파일: {pdf_path}")
# #     print("-" * 50)
# #
# #     # 밑줄 텍스트 추출 실행
# #     results = extract_underlined(pdf_path)
# #     # 1️⃣ 줄 깨짐 병합
# #     merged_results = merge_by_semicolon(results)
# #     # 2️⃣ 한 줄 내 다중 상품 분해
# #     final_results = split_products(merged_results)
# #
# #
# #     # 결과 출력
# #     if final_results:
# #         for r in final_results:
# #             print(f"[p{r['page']}] {r['text']}")
# #         print(f"\n총 {len(results)}개 밑줄 발견")
# #     else:
# #         print("밑줄 없음")
# #
# #     return final_results
# #
# #
# # if __name__ == "__main__":
# #     # --------------------------------------------------
# #     # 커맨드라인 인자 처리
# #     # --------------------------------------------------
# #     # python extract.py sample.pdf
# #     if len(sys.argv) > 1:
# #         path = sys.argv[1]
# #     else:
# #         # 인자가 없을 경우 기본 경로 사용
# #         path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/테스트/동일유사_1상표1출원1.pdf"
# #
# #     # 파일 존재 여부 확인
# #     if not Path(path).exists():
# #         print(f"파일 없음: {path}")
# #         sys.exit(1)
# #
# #     # 실행
# #     main(path)
#
#
#
# # 아래 로직은 밑줄이 포함된 데이터 추출
# # """
# # PDF에서 밑줄 친 텍스트를 추출하고
# # 해당 밑줄이 속한 상표(Filing number/International registration number)와 연결
# # """
# #
# # import re
# # import fitz
# # import sys
# # from pathlib import Path
# # from typing import List, Dict, Optional
# #
# #
# # def extract_trademark_sections(pdf_path):
# #     """
# #     PDF에서 상표 정보 섹션을 추출하여 각 섹션의 범위를 파악
# #
# #     return: [
# #         {
# #             "mark_number": 1,
# #             "filing_number": "4120080005100",
# #             "international_registration": None,
# #             "page_start": 2,
# #             "page_end": 2,
# #             "y_start": 200.5,
# #             "y_end": 450.3,
# #             "owner": "Han Nam Hee"
# #         },
# #         ...
# #     ]
# #     """
# #     doc = fitz.open(pdf_path)
# #     sections = []
# #
# #     # 모든 페이지에서 텍스트 블록과 위치 정보 추출
# #     all_blocks = []
# #     for page_num, page in enumerate(doc):
# #         blocks = page.get_text("dict")["blocks"]
# #         for block in blocks:
# #             if "lines" in block:
# #                 block_text = ""
# #                 for line in block["lines"]:
# #                     for span in line["spans"]:
# #                         block_text += span["text"] + " "
# #
# #                 all_blocks.append({
# #                     "page": page_num + 1,
# #                     "y0": block["bbox"][1],
# #                     "y1": block["bbox"][3],
# #                     "text": block_text.strip()
# #                 })
# #
# #     # "Information concerning the earlier mark" 패턴 찾기
# #     section_starts = []
# #     for idx, block in enumerate(all_blocks):
# #         match = re.search(
# #             r"Information concerning the earlier mark \((\d+)\)",
# #             block["text"],
# #             re.IGNORECASE
# #         )
# #         if match:
# #             section_starts.append({
# #                 "index": idx,
# #                 "mark_number": int(match.group(1)),
# #                 "page": block["page"],
# #                 "y": block["y0"]
# #             })
# #
# #     # 각 섹션의 범위 결정 및 정보 추출
# #     for i, start in enumerate(section_starts):
# #         # 섹션 끝 지점 결정
# #         if i + 1 < len(section_starts):
# #             end_idx = section_starts[i + 1]["index"]
# #             end_page = section_starts[i + 1]["page"]
# #             end_y = section_starts[i + 1]["y"]
# #         else:
# #             end_idx = len(all_blocks)
# #             end_page = all_blocks[-1]["page"]
# #             end_y = all_blocks[-1]["y1"]
# #
# #         # 해당 섹션의 텍스트 수집
# #         section_text = " ".join([
# #             all_blocks[j]["text"]
# #             for j in range(start["index"], end_idx)
# #         ])
# #
# #         # Filing number 추출 (고정 형식)
# #         filing_match = re.search(r"Filing number\s*:\s*(\d+)", section_text)
# #         filing_number = filing_match.group(1) if filing_match else None
# #
# #         # International registration number 추출 (고정 형식)
# #         ir_match = re.search(
# #             r"International registration number\s*:\s*(\d+)",
# #             section_text
# #         )
# #         international_registration = ir_match.group(1) if ir_match else None
# #
# #         # Owner 정보 추출
# #         owner_match = re.search(
# #             r"Name and address of the owner\s*:\s*([^\n]+)",
# #             section_text
# #         )
# #         owner = owner_match.group(1).strip() if owner_match else "Unknown"
# #
# #         sections.append({
# #             "mark_number": start["mark_number"],
# #             "filing_number": filing_number,
# #             "international_registration": international_registration,
# #             "page_start": start["page"],
# #             "page_end": end_page,
# #             "y_start": start["y"],
# #             "y_end": end_y,
# #             "owner": owner
# #         })
# #
# #     doc.close()
# #     return sections
# #
# #
# # def extract_underlined_with_positions(pdf_path):
# #     """
# #     PDF에서 밑줄 텍스트와 정확한 위치(페이지, y좌표) 추출
# #
# #     return: [
# #         {"page": 2, "y": 350.5, "text": "Advertising"},
# #         {"page": 2, "y": 365.2, "text": "presentation of goods..."},
# #         ...
# #     ]
# #     """
# #     doc = fitz.open(pdf_path)
# #     results = []
# #
# #     for page_num, page in enumerate(doc):
# #         drawings = page.get_drawings()
# #         lines = []
# #
# #         # 수평선 찾기
# #         for d in drawings:
# #             for item in d.get("items", []):
# #                 if item[0] == "l":
# #                     p1, p2 = item[1], item[2]
# #                     if abs(p1.y - p2.y) < 2:
# #                         length = abs(p2.x - p1.x)
# #                         if 10 < length < 500:
# #                             lines.append({
# #                                 "y": p1.y,
# #                                 "x0": min(p1.x, p2.x),
# #                                 "x1": max(p1.x, p2.x)
# #                             })
# #
# #         # 각 수평선 위의 텍스트 추출
# #         for line in lines:
# #             rect = fitz.Rect(
# #                 line["x0"] - 1,
# #                 line["y"] - 12,
# #                 line["x1"] + 1,
# #                 line["y"] + 1
# #             )
# #             text = page.get_text("text", clip=rect).strip()
# #             text = " ".join(text.split())
# #             text = normalize_underlined_text(text)
# #
# #             if text and len(text) > 1 and not should_exclude_underlined_text(text):
# #                 results.append({
# #                     "page": page_num + 1,
# #                     "y": line["y"],
# #                     "text": text
# #                 })
# #
# #     doc.close()
# #     return results
# #
# #
# # def normalize_underlined_text(text: str) -> str:
# #     """밑줄 텍스트 정규화"""
# #     text = text.strip()
# #     text = re.sub(
# #         r"^\(\s*underlined goods/services\s*\)\s*",
# #         "",
# #         text,
# #         flags=re.IGNORECASE
# #     )
# #     if re.search(r"goods/services\s*$", text, re.IGNORECASE):
# #         if not text.rstrip().endswith((';', '.')):
# #             text = text.rstrip() + ";"
# #     return text.strip()
# #
# #
# # def should_exclude_underlined_text(text: str) -> bool:
# #     """제외할 밑줄 텍스트 판단"""
# #     stripped = text.strip()
# #     if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
# #         return True
# #     if re.match(r"^(E-mail|Email|Telephone|Tel\.?|Fax)\s*:", stripped, re.IGNORECASE):
# #         return True
# #     if "@" in stripped:
# #         return True
# #     if stripped == "심사관 파트장 팀장 국장":
# #         return True
# #     return False
# #
# #
# # def match_underlines_to_sections(sections, underlines):
# #     """
# #     밑줄 데이터를 상표 섹션에 매칭
# #
# #     sections: extract_trademark_sections() 결과
# #     underlines: extract_underlined_with_positions() 결과
# #
# #     return: [
# #         {
# #             "mark_number": 1,
# #             "filing_number": "4120080005100",
# #             "international_registration": None,
# #             "owner": "Han Nam Hee",
# #             "underlined_goods": ["Advertising", "presentation of goods...", ...]
# #         },
# #         ...
# #     ]
# #     """
# #     results = []
# #
# #     for section in sections:
# #         # 이 섹션에 속하는 밑줄 찾기
# #         section_underlines = []
# #
# #         for u in underlines:
# #             # 페이지와 y좌표로 범위 판단
# #             in_page_range = (
# #                     section["page_start"] <= u["page"] <= section["page_end"]
# #             )
# #
# #             if in_page_range:
# #                 # 같은 페이지일 경우 y좌표도 확인
# #                 if u["page"] == section["page_start"]:
# #                     if u["y"] < section["y_start"]:
# #                         continue
# #                 if u["page"] == section["page_end"]:
# #                     if u["y"] > section["y_end"]:
# #                         continue
# #
# #                 section_underlines.append(u)
# #
# #         # 밑줄 텍스트 병합 및 분해
# #         if section_underlines:
# #             merged = merge_by_semicolon(section_underlines)
# #             final_goods = split_products(merged)
# #             goods_list = [item["text"] for item in final_goods]
# #         else:
# #             goods_list = []
# #
# #         results.append({
# #             "mark_number": section["mark_number"],
# #             "filing_number": section["filing_number"],
# #             "international_registration": section["international_registration"],
# #             "owner": section["owner"],
# #             "page_range": f"{section['page_start']}-{section['page_end']}",
# #             "underlined_goods": goods_list
# #         })
# #
# #     return results
# #
# #
# # def merge_by_semicolon(results):
# #     """세미콜론 기준 병합"""
# #     merged = []
# #     current_text = ""
# #     current_page = None
# #
# #     for item in results:
# #         text = item["text"]
# #         page = item["page"]
# #
# #         if current_page is not None and page != current_page:
# #             if current_text:
# #                 merged.append({
# #                     "page": current_page,
# #                     "text": current_text.rstrip(";.").strip()
# #                 })
# #                 current_text = ""
# #
# #         current_page = page
# #
# #         if current_text:
# #             current_text += " " + text
# #         else:
# #             current_text = text
# #
# #         if current_text.endswith(";") or current_text.endswith("."):
# #             merged.append({
# #                 "page": current_page,
# #                 "text": current_text.rstrip(";.").strip()
# #             })
# #             current_text = ""
# #
# #     if current_text:
# #         merged.append({
# #             "page": current_page,
# #             "text": current_text.rstrip(";.").strip()
# #         })
# #
# #     return merged
# #
# #
# # def split_products(merged_results):
# #     """세미콜론 기준 개별 상품 분해"""
# #     final_results = []
# #     for item in merged_results:
# #         page = item["page"]
# #         text = item["text"]
# #         parts = [p.strip() for p in text.split(";") if p.strip()]
# #         for part in parts:
# #             final_results.append({
# #                 "page": page,
# #                 "text": part
# #             })
# #     return final_results
# #
# #
# # def print_results(results):
# #     """결과를 보기 좋게 출력"""
# #     print("\n" + "=" * 80)
# #     print("상표별 밑줄 상품 분석 결과")
# #     print("=" * 80 + "\n")
# #
# #     for idx, r in enumerate(results, 1):
# #         print(f"[{idx}] 상표 정보")
# #         print(f"    Mark Number: {r['mark_number']}")
# #
# #         if r['filing_number']:
# #             print(f"    Filing Number: {r['filing_number']}")
# #         if r['international_registration']:
# #             print(f"    International Registration: {r['international_registration']}")
# #
# #         print(f"    Owner: {r['owner']}")
# #         print(f"    Page Range: {r['page_range']}")
# #         print(f"    Underlined Goods: {len(r['underlined_goods'])}개")
# #
# #         if r['underlined_goods']:
# #             print(f"\n    밑줄 친 상품 목록:")
# #             for i, goods in enumerate(r['underlined_goods'], 1):
# #                 print(f"      {i}. {goods}")
# #         else:
# #             print(f"    (밑줄 없음)")
# #
# #         print()
# #
# #
# # def main(pdf_path):
# #     """메인 실행 함수"""
# #     print(f"\n파일 분석 중: {pdf_path}")
# #     print("=" * 80)
# #
# #     # 1단계: 상표 섹션 추출
# #     print("\n[1단계] 상표 섹션 추출 중...")
# #     sections = extract_trademark_sections(pdf_path)
# #     print(f"✓ {len(sections)}개 상표 섹션 발견")
# #
# #     # 2단계: 밑줄 텍스트 추출
# #     print("\n[2단계] 밑줄 텍스트 추출 중...")
# #     underlines = extract_underlined_with_positions(pdf_path)
# #     print(f"✓ {len(underlines)}개 밑줄 발견")
# #
# #     # 3단계: 매칭
# #     print("\n[3단계] 상표-밑줄 매칭 중...")
# #     results = match_underlines_to_sections(sections, underlines)
# #     print(f"✓ 매칭 완료")
# #
# #     # 결과 출력
# #     print_results(results)
# #
# #     return results
# #
# #
# # if __name__ == "__main__":
# #     if len(sys.argv) > 1:
# #         path = sys.argv[1]
# #     else:
# #         path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/테스트/동일유사_1상표1출원1.pdf"
# #
# #     if not Path(path).exists():
# #         print(f"파일 없음: {path}")
# #         sys.exit(1)
# #
# #     main(path)
#
# """
# PDF에서 밑줄 친 텍스트를 추출하고
# 해당 밑줄이 속한 상표(Filing number/International registration number)와 연결
# """
#
# import re
# import fitz
# import sys
# from pathlib import Path
# from typing import List, Dict, Optional
#
#
# def extract_trademark_sections(pdf_path):
#     """
#     PDF에서 상표 정보 섹션을 추출하여 각 섹션의 범위를 파악
#
#     return: [
#         {
#             "filing_number": "4120080005100",
#             "international_registration": None,
#             "page_start": 2,
#             "page_end": 2,
#             "y_start": 200.5,
#             "y_end": 450.3
#         },
#         ...
#     ]
#     """
#     doc = fitz.open(pdf_path)
#     sections = []
#
#     # 모든 페이지에서 텍스트 블록과 위치 정보 추출
#     all_blocks = []
#     for page_num, page in enumerate(doc):
#         blocks = page.get_text("dict")["blocks"]
#         for block in blocks:
#             if "lines" in block:
#                 block_text = ""
#                 for line in block["lines"]:
#                     for span in line["spans"]:
#                         block_text += span["text"] + " "
#
#                 all_blocks.append({
#                     "page": page_num + 1,
#                     "y0": block["bbox"][1],
#                     "y1": block["bbox"][3],
#                     "text": block_text.strip()
#                 })
#
#     # "Information concerning the earlier mark" 패턴 찾기
#     # 두 가지 패턴 모두 지원: 번호 있음/없음
#     section_starts = []
#     for idx, block in enumerate(all_blocks):
#         # 패턴 1: 번호 있음 (1), (2), (3)...
#         match = re.search(
#             r"Information concerning the earlier mark \((\d+)\)",
#             block["text"],
#             re.IGNORECASE
#         )
#         if match:
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": int(match.group(1)),
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#             continue
#
#         # 패턴 2: 번호 없음
#         match = re.search(
#             r"Information concerning the earlier mark\s*$",
#             block["text"],
#             re.IGNORECASE
#         )
#         if match:
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": 1,  # 번호 없으면 1로 설정
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#
#     # 각 섹션의 범위 결정 및 정보 추출
#     for i, start in enumerate(section_starts):
#         # 섹션 끝 지점 결정
#         if i + 1 < len(section_starts):
#             end_idx = section_starts[i + 1]["index"]
#             end_page = section_starts[i + 1]["page"]
#             end_y = section_starts[i + 1]["y"]
#         else:
#             end_idx = len(all_blocks)
#             end_page = all_blocks[-1]["page"]
#             end_y = all_blocks[-1]["y1"]
#
#         # 해당 섹션의 텍스트 수집
#         section_text = " ".join([
#             all_blocks[j]["text"]
#             for j in range(start["index"], end_idx)
#         ])
#
#         # Filing number 추출 (고정 형식)
#         filing_match = re.search(r"Filing number\s*:\s*(\d+)", section_text)
#         filing_number = filing_match.group(1) if filing_match else None
#
#         # International registration number 추출 (고정 형식)
#         ir_match = re.search(
#             r"International registration number\s*:\s*(\d+)",
#             section_text
#         )
#         international_registration = ir_match.group(1) if ir_match else None
#
#         # Owner 정보 추출
#         owner_match = re.search(
#             r"Name and address of the owner\s*:\s*([^\n]+)",
#             section_text
#         )
#         owner = owner_match.group(1).strip() if owner_match else "Unknown"
#
#         sections.append({
#             "filing_number": filing_number,
#             "international_registration": international_registration,
#             "page_start": start["page"],
#             "page_end": end_page,
#             "y_start": start["y"],
#             "y_end": end_y
#         })
#
#     doc.close()
#     return sections
#
# def extract_underlined_with_positions(pdf_path):
#     """
#     PDF에서 밑줄 텍스트와 정확한 위치(페이지, y좌표) 추출
#
#     return: [
#         {"page": 2, "y": 350.5, "text": "Advertising"},
#         {"page": 2, "y": 365.2, "text": "presentation of goods..."},
#         ...
#     ]
#     """
#     doc = fitz.open(pdf_path)
#     results = []
#
#     for page_num, page in enumerate(doc):
#         drawings = page.get_drawings()
#         lines = []
#
#         # 수평선 찾기
#         for d in drawings:
#             for item in d.get("items", []):
#                 if item[0] == "l":
#                     p1, p2 = item[1], item[2]
#                     if abs(p1.y - p2.y) < 2:
#                         length = abs(p2.x - p1.x)
#                         if 10 < length < 500:
#                             lines.append({
#                                 "y": p1.y,
#                                 "x0": min(p1.x, p2.x),
#                                 "x1": max(p1.x, p2.x)
#                             })
#
#         # 각 수평선 위의 텍스트 추출
#         for line in lines:
#             rect = fitz.Rect(
#                 line["x0"] - 1,
#                 line["y"] - 12,
#                 line["x1"] + 1,
#                 line["y"] + 1
#             )
#             text = page.get_text("text", clip=rect).strip()
#             text = " ".join(text.split())
#             text = normalize_underlined_text(text)
#
#             if text and len(text) > 1 and not should_exclude_underlined_text(text):
#                 results.append({
#                     "page": page_num + 1,
#                     "y": line["y"],
#                     "text": text
#                 })
#
#     doc.close()
#     return results
#
# def normalize_underlined_text(text: str) -> str:
#     """밑줄 텍스트 정규화"""
#     text = text.strip()
#     text = re.sub(
#         r"^\(\s*underlined goods/services\s*\)\s*",
#         "",
#         text,
#         flags=re.IGNORECASE
#     )
#     if re.search(r"goods/services\s*$", text, re.IGNORECASE):
#         if not text.rstrip().endswith((';', '.')):
#             text = text.rstrip() + ";"
#     return text.strip()
#
# def should_exclude_underlined_text(text: str) -> bool:
#     """제외할 밑줄 텍스트 판단"""
#     stripped = text.strip()
#     if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
#         return True
#     if re.match(r"^(E-mail|Email|Telephone|Tel\.?|Fax)\s*:", stripped, re.IGNORECASE):
#         return True
#     if "@" in stripped:
#         return True
#     if stripped == "심사관 파트장 팀장 국장":
#         return True
#     return False
#
# def match_underlines_to_sections(sections, underlines):
#     """
#     밑줄 데이터를 상표 섹션에 매칭
#
#     sections: extract_trademark_sections() 결과
#     underlines: extract_underlined_with_positions() 결과
#
#     return: [
#         {
#             "filing_number": "4120080005100",
#             "international_registration": None,
#             "underlined_goods": ["Advertising", "presentation of goods...", ...]
#         },
#         ...
#     ]
#     """
#     results = []
#
#     for section in sections:
#         # 이 섹션에 속하는 밑줄 찾기
#         section_underlines = []
#
#         for u in underlines:
#             # 페이지와 y좌표로 범위 판단
#             in_page_range = (
#                 section["page_start"] <= u["page"] <= section["page_end"]
#             )
#
#             if in_page_range:
#                 # 같은 페이지일 경우 y좌표도 확인
#                 if u["page"] == section["page_start"]:
#                     if u["y"] < section["y_start"]:
#                         continue
#                 if u["page"] == section["page_end"]:
#                     if u["y"] > section["y_end"]:
#                         continue
#
#                 section_underlines.append(u)
#
#         # 밑줄 텍스트 병합 및 분해
#         if section_underlines:
#             merged = merge_by_semicolon(section_underlines)
#             final_goods = split_products(merged)
#             goods_list = [item["text"] for item in final_goods]
#         else:
#             goods_list = []
#
#         results.append({
#             "filing_number": section["filing_number"],
#             "international_registration": section["international_registration"],
#             "underlined_goods": goods_list
#         })
#
#     return results
#
# def merge_by_semicolon(results):
#     """세미콜론 기준 병합"""
#     merged = []
#     current_text = ""
#     current_page = None
#
#     for item in results:
#         text = item["text"]
#         page = item["page"]
#
#         if current_page is not None and page != current_page:
#             if current_text:
#                 merged.append({
#                     "page": current_page,
#                     "text": current_text.rstrip(";.").strip()
#                 })
#                 current_text = ""
#
#         current_page = page
#
#         if current_text:
#             current_text += " " + text
#         else:
#             current_text = text
#
#         if current_text.endswith(";") or current_text.endswith("."):
#             merged.append({
#                 "page": current_page,
#                 "text": current_text.rstrip(";.").strip()
#             })
#             current_text = ""
#
#     if current_text:
#         merged.append({
#             "page": current_page,
#             "text": current_text.rstrip(";.").strip()
#         })
#
#     return merged
#
# def split_products(merged_results):
#     """세미콜론 기준 개별 상품 분해"""
#     final_results = []
#     for item in merged_results:
#         page = item["page"]
#         text = item["text"]
#         parts = [p.strip() for p in text.split(";") if p.strip()]
#         for part in parts:
#             final_results.append({
#                 "page": page,
#                 "text": part
#             })
#     return final_results
#
# def print_results(results):
#     print(results)
#     """결과를 보기 좋게 출력"""
#     print("\n" + "=" * 80)
#     print("상표별 밑줄 상품 분석 결과")
#     print("=" * 80 + "\n")
#
#     for idx, r in enumerate(results, 1):
#         print(f"[{idx}] 상표 정보")
#
#         if r['filing_number']:
#             print(f"    Filing Number: {r['filing_number']}")
#         if r['international_registration']:
#             print(f"    International Registration: {r['international_registration']}")
#
#         print(f"    Underlined Goods: {len(r['underlined_goods'])}개")
#
#         if r['underlined_goods']:
#             print(f"\n    밑줄 친 상품 목록:")
#             for i, goods in enumerate(r['underlined_goods'], 1):
#                 print(f"      {i}. {goods}")
#         else:
#             print(f"    (밑줄 없음)")
#
#         print()
#
# def main(pdf_path):
#     """메인 실행 함수"""
#     print(f"\n파일 분석 중: {pdf_path}")
#     print("=" * 80)
#
#     # 1단계: 상표 섹션 추출
#     print("\n[1단계] 상표 섹션 추출 중...")
#     sections = extract_trademark_sections(pdf_path)
#     print(f"✓ {len(sections)}개 상표 섹션 발견")
#
#     # 2단계: 밑줄 텍스트 추출
#     print("\n[2단계] 밑줄 텍스트 추출 중...")
#     underlines = extract_underlined_with_positions(pdf_path)
#     print(f"✓ {len(underlines)}개 밑줄 발견")
#
#     # 3단계: 매칭
#     print("\n[3단계] 상표-밑줄 매칭 중...")
#     results = match_underlines_to_sections(sections, underlines)
#     print(f"✓ 매칭 완료")
#
#     # 결과 출력
#     print_results(results)
#
#     return results
#
# if __name__ == "__main__":
#     if len(sys.argv) > 1:
#         path = sys.argv[1]
#     else:
#         path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/테스트/식별력_1상표1출원.pdf"
#
#     if not Path(path).exists():
#         print(f"파일 없음: {path}")
#         sys.exit(1)
#
#     main(path)


# """
# PDF에서 밑줄 친 텍스트를 추출하고
# 해당 밑줄이 속한 상표(Filing number/International registration number)와 연결
# """
#
# import re
# import fitz
# import sys
# import asyncio
# from pathlib import Path
# from typing import List, Dict, Optional
# from concurrent.futures import ThreadPoolExecutor
#
#
# def extract_class_from_text(text: str) -> Optional[str]:
#     """텍스트에서 [Class XX] 패턴 추출"""
#     match = re.search(r'\[Class\s+(\d+)\]', text, re.IGNORECASE)
#     return match.group(1) if match else None
#
# def remove_class_prefix(text: str) -> str:
#     """텍스트에서 [Class XX] 부분 제거"""
#     return re.sub(r'\[Class\s+\d+\]\s*', '', text, flags=re.IGNORECASE).strip()
#
# def normalize_underlined_text(text: str) -> str:
#     """밑줄 텍스트 정규화"""
#     text = text.strip()
#     text = re.sub(
#         r"^\(\s*underlined goods/services\s*\)\s*",
#         "",
#         text,
#         flags=re.IGNORECASE
#     )
#     if re.search(r"goods/services\s*$", text, re.IGNORECASE):
#         if not text.rstrip().endswith((';', '.')):
#             text = text.rstrip() + ";"
#     return text.strip()
#
# def should_exclude_underlined_text(text: str) -> bool:
#     """제외할 밑줄 텍스트 판단"""
#     stripped = text.strip()
#     if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
#         return True
#     if re.match(r"^(E-mail|Email|Telephone|Tel\.?|Fax)\s*:", stripped, re.IGNORECASE):
#         return True
#     if "@" in stripped:
#         return True
#     if stripped == "심사관 파트장 팀장 국장":
#         return True
#     return False
#
# def extract_trademark_sections(pdf_path):
#     doc = fitz.open(pdf_path)
#     sections = []
#
#     # 모든 페이지에서 텍스트 블록과 위치 정보 추출
#     all_blocks = []
#     for page_num, page in enumerate(doc):
#         blocks = page.get_text("dict")["blocks"]
#         for block in blocks:
#             if "lines" in block:
#                 block_text = ""
#                 for line in block["lines"]:
#                     for span in line["spans"]:
#                         block_text += span["text"] + " "
#
#                 all_blocks.append({
#                     "page": page_num + 1,
#                     "y0": block["bbox"][1],
#                     "y1": block["bbox"][3],
#                     "text": block_text.strip()
#                 })
#
#     # "Information concerning the earlier mark" 패턴 찾기
#     section_starts = []
#     for idx, block in enumerate(all_blocks):
#         # 패턴 1: 번호 있음
#         match = re.search(
#             r"Information concerning the earlier mark \((\d+)\)",
#             block["text"],
#             re.IGNORECASE
#         )
#         if match:
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": int(match.group(1)),
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#             continue
#
#         # 패턴 2: 번호 없음
#         match = re.search(
#             r"Information concerning the earlier mark\s*$",
#             block["text"],
#             re.IGNORECASE
#         )
#         if match:
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": 1,
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#
#     # 섹션이 없는 경우: 전체 문서를 하나의 섹션으로 처리
#     if not section_starts:
#         full_text = " ".join([block["text"] for block in all_blocks])
#
#         filing_match = re.search(r"Filing number\s*:\s*(\d+)", full_text)
#         filing_number = filing_match.group(1) if filing_match else None
#
#         ir_match = re.search(
#             r"International Registration/Subsequent Designation No[.\s]*.*?:\s*(\d+)",
#             full_text
#         )
#         international_registration = ir_match.group(1) if ir_match else None
#
#         doc.close()
#         return [{
#             "filing_number": filing_number,
#             "international_registration": international_registration,
#             "page_start": 1,
#             "page_end": all_blocks[-1]["page"] if all_blocks else 1,
#             "y_start": 0,
#             "y_end": float('inf')
#         }]
#
#     # 각 섹션의 범위 결정 및 정보 추출
#     for i, start in enumerate(section_starts):
#         if i + 1 < len(section_starts):
#             end_idx = section_starts[i + 1]["index"]
#             end_page = section_starts[i + 1]["page"]
#             end_y = section_starts[i + 1]["y"]
#         else:
#             end_idx = len(all_blocks)
#             end_page = all_blocks[-1]["page"]
#             end_y = all_blocks[-1]["y1"]
#
#         section_text = " ".join([
#             all_blocks[j]["text"]
#             for j in range(start["index"], end_idx)
#         ])
#
#         filing_match = re.search(r"Filing number\s*:\s*(\d+)", section_text)
#         filing_number = filing_match.group(1) if filing_match else None
#
#         ir_match = re.search(
#             r"International registration number\s*:\s*(\d+)",
#             section_text
#         )
#         international_registration = ir_match.group(1) if ir_match else None
#
#         sections.append({
#             "filing_number": filing_number,
#             "international_registration": international_registration,
#             "page_start": start["page"],
#             "page_end": end_page,
#             "y_start": start["y"],
#             "y_end": end_y
#         })
#
#     doc.close()
#     return sections
#
# def extract_underlined_with_positions(pdf_path):
#     """PDF에서 밑줄 텍스트와 정확한 위치(페이지, y좌표) 추출"""
#     doc = fitz.open(pdf_path)
#     results = []
#
#     for page_num, page in enumerate(doc):
#         drawings = page.get_drawings()
#         lines = []
#
#         # 수평선 찾기
#         for d in drawings:
#             for item in d.get("items", []):
#                 if item[0] == "l":
#                     p1, p2 = item[1], item[2]
#                     if abs(p1.y - p2.y) < 2:
#                         length = abs(p2.x - p1.x)
#                         if 10 < length < 500:
#                             lines.append({
#                                 "y": p1.y,
#                                 "x0": min(p1.x, p2.x),
#                                 "x1": max(p1.x, p2.x)
#                             })
#
#         # 각 수평선 위의 텍스트 추출
#         for line in lines:
#             rect = fitz.Rect(
#                 line["x0"] - 1,
#                 line["y"] - 12,
#                 line["x1"] + 1,
#                 line["y"] + 1
#             )
#             text = page.get_text("text", clip=rect).strip()
#             text = " ".join(text.split())
#
#             # Class 정보 추출 (정규화 전에)
#             class_num = extract_class_from_text(text)
#
#             # 텍스트 정규화
#             text = normalize_underlined_text(text)
#
#             if text and len(text) > 1 and not should_exclude_underlined_text(text):
#                 results.append({
#                     "page": page_num + 1,
#                     "y": line["y"],
#                     "text": text,
#                     "class": class_num
#                 })
#
#     doc.close()
#     return results
#
# def match_underlines_to_sections(sections, underlines):
#     """밑줄 데이터를 상표 섹션에 매칭"""
#     results = []
#
#     for section in sections:
#         section_underlines = []
#
#         for u in underlines:
#             in_page_range = (
#                     section["page_start"] <= u["page"] <= section["page_end"]
#             )
#
#             if in_page_range:
#                 if u["page"] == section["page_start"]:
#                     if u["y"] < section["y_start"]:
#                         continue
#                 if u["page"] == section["page_end"]:
#                     if u["y"] > section["y_end"]:
#                         continue
#
#                 section_underlines.append(u)
#
#         # 밑줄 텍스트 병합 및 분해
#         if section_underlines:
#             merged = merge_by_semicolon(section_underlines)
#             final_goods = split_products(merged)
#
#             # Class 정보와 함께 구조화
#             goods_list = []
#             for item in final_goods:
#                 goods_list.append({
#                     "class": item.get("class"),
#                     "goods": item["text"]
#                 })
#         else:
#             goods_list = []
#
#         results.append({
#             "filing_number": section["filing_number"],
#             "international_registration": section["international_registration"],
#             "underlined_goods": goods_list
#         })
#
#     return results
#
# def merge_by_semicolon(results):
#     """세미콜론 기준 병합 (Class 정보 유지)"""
#     merged = []
#     current_text = ""
#     current_page = None
#     current_class = None
#
#     for item in results:
#         text = item["text"]
#         page = item["page"]
#         class_num = item.get("class")
#
#         if current_page is not None and page != current_page:
#             if current_text:
#                 merged.append({
#                     "page": current_page,
#                     "text": current_text.rstrip(";.").strip(),
#                     "class": current_class
#                 })
#                 current_text = ""
#                 current_class = None
#
#         current_page = page
#
#         if class_num and not current_class:
#             current_class = class_num
#
#         if current_text:
#             current_text += " " + text
#         else:
#             current_text = text
#
#         if current_text.endswith(";") or current_text.endswith("."):
#             merged.append({
#                 "page": current_page,
#                 "text": current_text.rstrip(";.").strip(),
#                 "class": current_class
#             })
#             current_text = ""
#             current_class = None
#
#     if current_text:
#         merged.append({
#             "page": current_page,
#             "text": current_text.rstrip(";.").strip(),
#             "class": current_class
#         })
#
#     return merged
#
# def split_products(merged_results):
#     """세미콜론 기준 개별 상품 분해 (Class 정보 유지)"""
#     final_results = []
#     for item in merged_results:
#         page = item["page"]
#         text = item["text"]
#         class_num = item.get("class")
#
#         text_without_class = remove_class_prefix(text)
#         parts = [p.strip() for p in text_without_class.split(";") if p.strip()]
#
#         for part in parts:
#             final_results.append({
#                 "page": page,
#                 "text": part,
#                 "class": class_num
#             })
#     return final_results
#
# def extract_underlined_goods_sync(pdf_path):
#     """동기 함수: PDF에서 상표별 밑줄 상품 추출"""
#     sections = extract_trademark_sections(pdf_path)
#     underlines = extract_underlined_with_positions(pdf_path)
#     results = match_underlines_to_sections(sections, underlines)
#     return results
#
# async def extract_underlined_goods_async(pdf_path):
#     """비동기 함수: PDF에서 상표별 밑줄 상품 추출"""
#     loop = asyncio.get_event_loop()
#
#     with ThreadPoolExecutor() as executor:
#         results = await loop.run_in_executor(
#             executor,
#             extract_underlined_goods_sync,
#             pdf_path
#         )
#
#     return results
#
# async def extract_underline(file_path: str):
#     import logging
#     logger = logging.getLogger(__name__)
#
#     logger.info("PDF UNDERLINE 추출 프로세스 시작.")
#
#     try:
#         if not Path(file_path).exists():
#             logger.error(f"파일을 찾을 수 없음: {file_path}")
#             return []
#
#         results = await extract_underlined_goods_async(file_path)
#
#         logger.info(f"PDF UNDERLINE 추출 완료: {len(results)}개 상표 처리")
#         logger.info("PDF UNDERLINE 추출 프로세스 완료.")
#
#         return results
#
#     except Exception as e:
#         logger.error(f"PDF UNDERLINE 추출 중 오류 발생: {str(e)}", exc_info=True)
#         return []
#
# def print_results(results):
#     """결과를 보기 좋게 출력"""
#     print("\n결과 데이터:")
#     print(results)
#
#     print("\n" + "=" * 80)
#     print("상표별 밑줄 상품 분석 결과")
#     print("=" * 80 + "\n")
#
#     for idx, r in enumerate(results, 1):
#         print(f"[{idx}] 상표 정보")
#
#         if r['filing_number']:
#             print(f"    Filing Number: {r['filing_number']}")
#         if r['international_registration']:
#             print(f"    International Registration: {r['international_registration']}")
#
#         print(f"    Underlined Goods: {len(r['underlined_goods'])}개")
#
#         if r['underlined_goods']:
#             print(f"\n    밑줄 친 상품 목록:")
#             for i, goods_item in enumerate(r['underlined_goods'], 1):
#                 class_info = f"[Class {goods_item['class']}] " if goods_item['class'] else ""
#                 print(f"      {i}. {class_info}{goods_item['goods']}")
#         else:
#             print(f"    (밑줄 없음)")
#
#         print()
#
# def main(pdf_path):
#     """메인 실행 함수"""
#     print(f"\n파일 분석 중: {pdf_path}")
#     print("=" * 80)
#
#     print("\n[1단계] 상표 섹션 추출 중...")
#     sections = extract_trademark_sections(pdf_path)
#     print(f"✓ {len(sections)}개 상표 섹션 발견")
#
#     print("\n[2단계] 밑줄 텍스트 추출 중...")
#     underlines = extract_underlined_with_positions(pdf_path)
#     print(f"✓ {len(underlines)}개 밑줄 발견")
#
#     print("\n[3단계] 상표-밑줄 매칭 중...")
#     results = match_underlines_to_sections(sections, underlines)
#     print(f"✓ 매칭 완료")
#
#     print_results(results)
#
#     return results
#
#
# if __name__ == "__main__":
#     if len(sys.argv) > 1:
#         path = sys.argv[1]
#     else:
#         path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/테스트/동일유사3.pdf"
#
#     if not Path(path).exists():
#         print(f"파일 없음: {path}")
#         sys.exit(1)
#
#     main(path)

# 최종으로 사용하려고 했지만 인용 상표 전체를 가져오지 못하는 상황 발생으로 사용하지 않음.
# """
# PDF에서 밑줄 친 텍스트를 추출하고
# 해당 밑줄이 속한 상표(Filing number/International registration number)와 연결
# """
#
# import re
# import fitz
# import sys
# import asyncio
# from pathlib import Path
# from typing import List, Dict, Optional
# from concurrent.futures import ThreadPoolExecutor
#
#
# def extract_class_from_text(text: str) -> Optional[str]:
#     """텍스트에서 [Class XX] 패턴 추출"""
#     match = re.search(r'\[Class\s+(\d+)\]', text, re.IGNORECASE)
#     return match.group(1) if match else None
#
#
# def remove_class_prefix(text: str) -> str:
#     """텍스트에서 [Class XX] 부분 제거"""
#     return re.sub(r'\[Class\s+\d+\]\s*', '', text, flags=re.IGNORECASE).strip()
#
#
# def normalize_underlined_text(text: str, remove_class: bool = False) -> str:
#     """
#     밑줄 텍스트 정규화
#
#     Args:
#         text: 정규화할 텍스트
#         remove_class: [Class XX] 부분도 제거할지 여부
#     """
#     text = text.strip()
#
#     # (underlined goods/services) prefix 제거
#     text = re.sub(
#         r"^\(\s*underlined goods/services\s*\)\s*",
#         "",
#         text,
#         flags=re.IGNORECASE
#     )
#
#     # [Class XX] 제거 (옵션)
#     if remove_class:
#         text = remove_class_prefix(text)
#
#     # goods/services로 끝나는 경우 세미콜론 보정
#     if re.search(r"goods/services\s*$", text, re.IGNORECASE):
#         if not text.rstrip().endswith((';', '.')):
#             text = text.rstrip() + ";"
#
#     return text.strip()
#
#
# def should_exclude_underlined_text(text: str) -> bool:
#     """제외할 밑줄 텍스트 판단"""
#     stripped = text.strip()
#     if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
#         return True
#     if re.match(r"^(E-mail|Email|Telephone|Tel\.?|Fax)\s*:", stripped, re.IGNORECASE):
#         return True
#     if "@" in stripped:
#         return True
#     if stripped == "심사관 파트장 팀장 국장":
#         return True
#     if stripped == "심사관 팀장 국장":
#         return True
#     return False
#
#
# def extract_trademark_sections(pdf_path):
#     """PDF에서 상표 정보 섹션을 추출하여 각 섹션의 범위를 파악"""
#     doc = fitz.open(pdf_path)
#     sections = []
#
#     # 모든 페이지에서 텍스트 블록과 위치 정보 추출
#     all_blocks = []
#     for page_num, page in enumerate(doc):
#         blocks = page.get_text("dict")["blocks"]
#         for block in blocks:
#             if "lines" in block:
#                 block_text = ""
#                 for line in block["lines"]:
#                     for span in line["spans"]:
#                         block_text += span["text"] + " "
#
#                 all_blocks.append({
#                     "page": page_num + 1,
#                     "y0": block["bbox"][1],
#                     "y1": block["bbox"][3],
#                     "text": block_text.strip()
#                 })
#
#     # "Information concerning the earlier mark" 패턴 찾기
#     section_starts = []
#     for idx, block in enumerate(all_blocks):
#         # 패턴 1: 번호 있음
#         match = re.search(
#             r"Information concerning the earlier mark \((\d+)\)",
#             block["text"],
#             re.IGNORECASE
#         )
#         if match:
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": int(match.group(1)),
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#             continue
#
#         # 패턴 2: 번호 없음
#         match = re.search(
#             r"Information concerning the earlier mark\s*$",
#             block["text"],
#             re.IGNORECASE
#         )
#         if match:
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": 1,
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#
#     # 섹션이 없는 경우: 전체 문서를 하나의 섹션으로 처리
#     if not section_starts:
#         full_text = " ".join([block["text"] for block in all_blocks])
#
#         filing_match = re.search(r"Filing number\s*:\s*(\d+)", full_text)
#         filing_number = filing_match.group(1) if filing_match else None
#
#         ir_match = re.search(
#             r"International Registration/Subsequent Designation No[.\s]*.*?:\s*(\d+)",
#             full_text
#         )
#         international_registration = ir_match.group(1) if ir_match else None
#
#         doc.close()
#         return [{
#             "filing_number": filing_number,
#             "international_registration": international_registration,
#             "page_start": 1,
#             "page_end": all_blocks[-1]["page"] if all_blocks else 1,
#             "y_start": 0,
#             "y_end": float('inf')
#         }]
#
#     # 각 섹션의 범위 결정 및 정보 추출
#     for i, start in enumerate(section_starts):
#         if i + 1 < len(section_starts):
#             end_idx = section_starts[i + 1]["index"]
#             end_page = section_starts[i + 1]["page"]
#             end_y = section_starts[i + 1]["y"]
#         else:
#             end_idx = len(all_blocks)
#             end_page = all_blocks[-1]["page"]
#             end_y = all_blocks[-1]["y1"]
#
#         section_text = " ".join([
#             all_blocks[j]["text"]
#             for j in range(start["index"], end_idx)
#         ])
#
#         filing_match = re.search(r"Filing number\s*:\s*(\d+)", section_text)
#         filing_number = filing_match.group(1) if filing_match else None
#
#         ir_match = re.search(
#             r"International registration number\s*:\s*(\d+)",
#             section_text
#         )
#         international_registration = ir_match.group(1) if ir_match else None
#
#         sections.append({
#             "filing_number": filing_number,
#             "international_registration": international_registration,
#             "page_start": start["page"],
#             "page_end": end_page,
#             "y_start": start["y"],
#             "y_end": end_y
#         })
#
#     doc.close()
#     return sections
#
#
# def extract_underlined_with_positions(pdf_path):
#     """PDF에서 밑줄 텍스트와 정확한 위치(페이지, y좌표) 추출"""
#     doc = fitz.open(pdf_path)
#     results = []
#
#     for page_num, page in enumerate(doc):
#         drawings = page.get_drawings()
#         lines = []
#
#         # 수평선 찾기
#         for d in drawings:
#             for item in d.get("items", []):
#                 if item[0] == "l":
#                     p1, p2 = item[1], item[2]
#                     if abs(p1.y - p2.y) < 2:
#                         length = abs(p2.x - p1.x)
#                         if 10 < length < 500:
#                             lines.append({
#                                 "y": p1.y,
#                                 "x0": min(p1.x, p2.x),
#                                 "x1": max(p1.x, p2.x)
#                             })
#
#         # 각 수평선 위의 텍스트 추출
#         for line in lines:
#             rect = fitz.Rect(
#                 line["x0"] - 1,
#                 line["y"] - 12,
#                 line["x1"] + 1,
#                 line["y"] + 1
#             )
#             text = page.get_text("text", clip=rect).strip()
#             text = " ".join(text.split())
#
#             # ⭐ 중요: Class 정보를 먼저 추출 (정규화 전 원본 텍스트에서)
#             original_text = text
#             class_num = extract_class_from_text(original_text)
#
#             # 텍스트 정규화 (Class는 아직 제거하지 않음)
#             text = normalize_underlined_text(text, remove_class=False)
#
#             if text and len(text) > 1 and not should_exclude_underlined_text(text):
#                 results.append({
#                     "page": page_num + 1,
#                     "y": line["y"],
#                     "text": text,
#                     "class": class_num
#                 })
#
#     doc.close()
#     return results
#
#
# def match_underlines_to_sections(sections, underlines):
#     """밑줄 데이터를 상표 섹션에 매칭"""
#     results = []
#
#     for section in sections:
#         section_underlines = []
#
#         for u in underlines:
#             in_page_range = (
#                     section["page_start"] <= u["page"] <= section["page_end"]
#             )
#
#             if in_page_range:
#                 if u["page"] == section["page_start"]:
#                     if u["y"] < section["y_start"]:
#                         continue
#                 if u["page"] == section["page_end"]:
#                     if u["y"] > section["y_end"]:
#                         continue
#
#                 section_underlines.append(u)
#
#         # 밑줄 텍스트 병합 및 분해
#         if section_underlines:
#             merged = merge_by_semicolon(section_underlines)
#             final_goods = split_products(merged)
#
#             # Class 정보와 함께 구조화
#             goods_list = []
#             for item in final_goods:
#                 goods_list.append({
#                     "class": item.get("class"),
#                     "goods": item["text"]
#                 })
#         else:
#             goods_list = []
#
#         results.append({
#             "filing_number": section["filing_number"],
#             "international_registration": section["international_registration"],
#             "underlined_goods": goods_list
#         })
#
#     return results
#
#
# def merge_by_semicolon(results):
#     """세미콜론 기준 병합 (Class 정보 유지)"""
#     merged = []
#     current_text = ""
#     current_page = None
#     current_class = None
#
#     for item in results:
#         text = item["text"]
#         page = item["page"]
#         class_num = item.get("class")
#
#         if current_page is not None and page != current_page:
#             if current_text:
#                 merged.append({
#                     "page": current_page,
#                     "text": current_text.rstrip(";.").strip(),
#                     "class": current_class
#                 })
#                 current_text = ""
#                 current_class = None
#
#         current_page = page
#
#         if class_num and not current_class:
#             current_class = class_num
#
#         if current_text:
#             current_text += " " + text
#         else:
#             current_text = text
#
#         if current_text.endswith(";") or current_text.endswith("."):
#             merged.append({
#                 "page": current_page,
#                 "text": current_text.rstrip(";.").strip(),
#                 "class": current_class
#             })
#             current_text = ""
#             current_class = None
#
#     if current_text:
#         merged.append({
#             "page": current_page,
#             "text": current_text.rstrip(";.").strip(),
#             "class": current_class
#         })
#
#     return merged
#
#
# def split_products(merged_results):
#     """세미콜론 기준 개별 상품 분해 (Class 정보 유지)"""
#     final_results = []
#     for item in merged_results:
#         page = item["page"]
#         text = item["text"]
#         class_num = item.get("class")
#
#         # [Class XX] 제거 후 분해
#         text_without_class = remove_class_prefix(text)
#
#         # 세미콜론으로 분해
#         parts = [p.strip() for p in text_without_class.split(";") if p.strip()]
#
#         for part in parts:
#             final_results.append({
#                 "page": page,
#                 "text": part,
#                 "class": class_num
#             })
#
#     return final_results
#
#
# def extract_underlined_goods_sync(pdf_path):
#     """동기 함수: PDF에서 상표별 밑줄 상품 추출"""
#     sections = extract_trademark_sections(pdf_path)
#     underlines = extract_underlined_with_positions(pdf_path)
#     results = match_underlines_to_sections(sections, underlines)
#     return results
#
#
# async def extract_underlined_goods_async(pdf_path):
#     """비동기 함수: PDF에서 상표별 밑줄 상품 추출"""
#     loop = asyncio.get_event_loop()
#
#     with ThreadPoolExecutor() as executor:
#         results = await loop.run_in_executor(
#             executor,
#             extract_underlined_goods_sync,
#             pdf_path
#         )
#
#     return results
#
#
# async def extract_underline(file_path: str):
#     """
#     PDF에서 상표별 밑줄 상품을 추출하는 메인 함수
#
#     Returns:
#         list: [
#             {
#                 'filing_number': '4120080005100',
#                 'international_registration': None,
#                 'underlined_goods': [
#                     {"class": "35", "goods": "Advertising"},
#                     ...
#                 ]
#             },
#             ...
#         ]
#     """
#     import logging
#     logger = logging.getLogger(__name__)
#
#     logger.info("PDF UNDERLINE 추출 프로세스 시작.")
#
#     try:
#         if not Path(file_path).exists():
#             logger.error(f"파일을 찾을 수 없음: {file_path}")
#             return []
#
#         results = await extract_underlined_goods_async(file_path)
#
#         logger.info(f"PDF UNDERLINE 추출 완료: {len(results)}개 상표 처리")
#         logger.info("PDF UNDERLINE 추출 프로세스 완료.")
#
#         return results
#
#     except Exception as e:
#         logger.error(f"PDF UNDERLINE 추출 중 오류 발생: {str(e)}", exc_info=True)
#         return []
#
#
# def print_results(results):
#     """결과를 보기 좋게 출력"""
#     print("\n결과 데이터:")
#     print(results)
#
#     print("\n" + "=" * 80)
#     print("상표별 밑줄 상품 분석 결과")
#     print("=" * 80 + "\n")
#
#     for idx, r in enumerate(results, 1):
#         print(f"[{idx}] 상표 정보")
#
#         if r['filing_number']:
#             print(f"    Filing Number: {r['filing_number']}")
#         if r['international_registration']:
#             print(f"    International Registration: {r['international_registration']}")
#
#         print(f"    Underlined Goods: {len(r['underlined_goods'])}개")
#
#         if r['underlined_goods']:
#             print(f"\n    밑줄 친 상품 목록:")
#             for i, goods_item in enumerate(r['underlined_goods'], 1):
#                 class_info = f"[Class {goods_item['class']}] " if goods_item['class'] else ""
#                 print(f"      {i}. {class_info}{goods_item['goods']}")
#         else:
#             print(f"    (밑줄 없음)")
#
#         print()
#
#
# def main(pdf_path):
#     """메인 실행 함수"""
#     print(f"\n파일 분석 중: {pdf_path}")
#     print("=" * 80)
#
#     print("\n[1단계] 상표 섹션 추출 중...")
#     sections = extract_trademark_sections(pdf_path)
#     print(f"✓ {len(sections)}개 상표 섹션 발견")
#
#     print("\n[2단계] 밑줄 텍스트 추출 중...")
#     underlines = extract_underlined_with_positions(pdf_path)
#     print(f"✓ {len(underlines)}개 밑줄 발견")
#
#     # 디버깅: 추출된 밑줄 확인
#     print("\n추출된 밑줄 샘플 (처음 3개):")
#     for i, u in enumerate(underlines[:3]):
#         print(f"  {i + 1}. Page={u['page']}, Class={u['class']}, Text={u['text'][:50]}...")
#
#     print("\n[3단계] 상표-밑줄 매칭 중...")
#     results = match_underlines_to_sections(sections, underlines)
#     print(f"✓ 매칭 완료")
#
#     print_results(results)
#
#     return results
#
#
# if __name__ == "__main__":
#     if len(sys.argv) > 1:
#         path = sys.argv[1]
#     else:
#         path = r"/home/mark15/project/markpass/markpass-file/example_opinion/가거절 통지서/552025075457917-01-복사.pdf"
#
#     if not Path(path).exists():
#         print(f"파일 없음: {path}")
#         sys.exit(1)
#
#     main(path)

for i in range(5):
    print(i-i)

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
import asyncio
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

def extract_trademark_sections(pdf_path):
    """
    PDF에서 'Information concerning the earlier mark' 섹션을 기준으로
    각 상표(Earlier Mark)의 범위를 추출하는 함수
    """

    print("\n[START] extract_trademark_sections")
    print(f"PDF PATH: {pdf_path}")

    # PDF 열기
    doc = fitz.open(pdf_path)

    # 최종 섹션 결과
    sections = []

    # ==================================================
    # 1️⃣ 모든 페이지에서 텍스트 블록 수집
    # ==================================================
    all_blocks = []

    for page_num, page in enumerate(doc):
        print(f"\n--- Page {page_num + 1} 처리 시작 ---")

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

            print(f"[BLOCK] page={block_info['page']} y0={block_info['y0']:.2f} "
                  f"text='{block_text[:80]}'")

            all_blocks.append(block_info)

    print(f"\n[INFO] 전체 블록 수집 완료: {len(all_blocks)}개")

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
            print(f"[SECTION START] idx={idx}, mark_number={mark_number}, "
                  f"page={block['page']}, y={block['y0']:.2f}")

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
            print(f"[SECTION START - NO NUMBER] idx={idx}, page={block['page']}")

            section_starts.append({
                "index": idx,
                "mark_number": 1,
                "page": block["page"],
                "y": block["y0"]
            })

    print(f"\n[INFO] 섹션 시작점 개수: {len(section_starts)}")

    # ==================================================
    # 3️⃣ 섹션 시작점이 아예 없는 PDF 처리
    # ==================================================
    if not section_starts:
        print("[WARN] 섹션 헤더 미발견 → 전체 문서를 하나의 상표로 처리")

        full_text = " ".join([block["text"] for block in all_blocks])

        filing_match = re.search(r"Filing number\s*:\s*(\d+)", full_text)
        filing_number = filing_match.group(1) if filing_match else None

        ir_match = re.search(
            r"International\s+(?:Registration|registration)[/\s]+"
            r"Subsequent\s+Designation\s+No[.\s]*:?\s*(\d+)",
            full_text
        )
        international_registration = ir_match.group(1) if ir_match else None

        print(f"[INFO] Filing Number: {filing_number}")
        print(f"[INFO] International Reg.: {international_registration}")

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
        print(f"\n[PROCESS SECTION] mark_number={start['mark_number']}")

        # 다음 섹션이 있으면 거기 전까지
        if i + 1 < len(section_starts):
            end_idx = section_starts[i + 1]["index"]
            end_page = section_starts[i + 1]["page"]
            end_y = section_starts[i + 1]["y"]
        else:
            end_idx = len(all_blocks)
            end_page = all_blocks[-1]["page"]
            end_y = all_blocks[-1]["y1"]

        print(f"  page_start={start['page']} y_start={start['y']:.2f}")
        print(f"  page_end={end_page} y_end={end_y:.2f}")

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

        print(f"  Filing Number: {filing_number}")
        print(f"  International Reg.: {international_registration}")

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

    print("\n[END] extract_trademark_sections")
    print(f"[RESULT] sections={sections}")

    return sections

def extract_underlined_with_positions(pdf_path):
    """
    PDF에서 '밑줄(underline)'에 해당하는 수평선을 직접 탐지하고,
    해당 수평선 바로 위에 위치한 텍스트를 추출하는 함수

    ✔ 텍스트 스타일(underline 속성)을 쓰지 않고
    ✔ PDF 내부에 실제로 그려진 '수평선(line)'을 기준으로 판단함
    """

    print("\n[START] extract_underlined_with_positions")
    print(f"[INFO] PDF PATH = {pdf_path}")

    # ==================================================
    # 0️⃣ PDF 파일 오픈
    # ==================================================
    # fitz.open() : PyMuPDF에서 PDF 문서를 여는 공식 API
    doc = fitz.open(pdf_path)

    # 최종 결과를 누적할 리스트
    # 각 원소는 {page, y, text, class} 형태의 dict
    results = []

    # ==================================================
    # 1️⃣ 페이지 단위로 PDF 순회
    # ==================================================
    # enumerate → (페이지 인덱스, 페이지 객체)
    for page_num, page in enumerate(doc):
        print(f"\n==============================")
        print(f"[PAGE START] Page {page_num + 1}")
        print(f"==============================")

        # --------------------------------------------------
        # page.get_drawings()
        # --------------------------------------------------
        # PyMuPDF(fitz) 내장 메서드
        # 해당 페이지에 '그려진 모든 그래픽 객체'를 반환
        #
        # 포함 예:
        # - 선(line)
        # - 사각형(rect)
        # - 테두리
        # - 밑줄 (underline)
        #
        # ❌ 텍스트는 포함되지 않음
        drawings = page.get_drawings()
        print(f"[INFO] total drawings = {len(drawings)}")

        # 밑줄로 의심되는 '수평선 후보'를 모을 리스트
        lines = []

        # ==================================================
        # 2️⃣ 그래픽 객체 중 수평선(underline) 탐색
        # ==================================================
        for d_idx, d in enumerate(drawings):
            print(f"\n  [DRAWING {d_idx + 1}] items = {len(d.get('items', []))}")

            # drawings 안의 실제 객체들은 d["items"]에 들어있음
            for item in d.get("items", []):

                # item[0] == "l"  → line (선)
                # item 구조 예:
                # ("l", Point(x1,y1), Point(x2,y2))
                if item[0] == "l":
                    p1, p2 = item[1], item[2]

                    # ------------------------------------------
                    # 수평선 판별 조건
                    # ------------------------------------------
                    # y 좌표 차이가 거의 없으면 수평선
                    if abs(p1.y - p2.y) < 2:
                        length = abs(p2.x - p1.x)

                        # ------------------------------------------
                        # 밑줄로 볼 수 있는 길이만 허용
                        # 너무 짧으면 노이즈
                        # 너무 길면 페이지 구분선/표 테두리 가능성
                        # ------------------------------------------
                        if 10 < length < 500:
                            line_info = {
                                "y": p1.y,
                                "x0": min(p1.x, p2.x),
                                "x1": max(p1.x, p2.x)
                            }

                            print(
                                f"  [UNDERLINE FOUND] "
                                f"y={p1.y:.2f}, "
                                f"x0={line_info['x0']:.2f}, "
                                f"x1={line_info['x1']:.2f}, "
                                f"length={length:.2f}"
                            )

                            # 밑줄 후보로 저장
                            lines.append(line_info)

        print(f"\n[INFO] underline candidates found = {len(lines)}")

        # ==================================================
        # 3️⃣ 각 밑줄 위의 텍스트 추출
        # ==================================================
        for idx, line in enumerate(lines):
            print(f"\n------------------------------")
            print(f"[PROCESS LINE {idx + 1}] y={line['y']:.2f}")
            print(f"------------------------------")

            # ------------------------------------------
            # 밑줄 바로 '위' 영역을 clip 영역으로 설정
            # ------------------------------------------
            # PDF 좌표계:
            # - y 값이 커질수록 아래쪽
            #
            # 따라서:
            # y - 12 ~ y + 1 영역이
            # '밑줄 바로 위의 텍스트 영역'
            rect = fitz.Rect(
                line["x0"] - 1,
                line["y"] - 12,   # ⬅️ 밑줄 위쪽 텍스트 영역
                line["x1"] + 1,
                line["y"] + 1
            )

            # ------------------------------------------
            # clip 영역 내 텍스트 추출
            # ------------------------------------------
            raw_text = page.get_text("text", clip=rect)
            if raw_text == '심사관\n파트장\n팀장\n국장\n':
                continue

            # repr 사용 → \n, \t 같은 제어문자 확인 목적
            print(f"[RAW TEXT] {repr(raw_text)}")

            # ------------------------------------------
            # 텍스트 정리
            # - 앞뒤 공백 제거
            # - 줄바꿈, 연속 공백 → 단일 공백
            # ------------------------------------------
            text = raw_text.strip()
            text = " ".join(text.split())

            print(f"[CLEAN TEXT] '{text}'")

            # ==================================================
            # 4️⃣ Class 정보 추출 ([Class XX])
            # ==================================================
            original_text = text

            match = re.search(
                r'\[Class\s+(\d+)\]',
                original_text,
                re.IGNORECASE
            )

            class_num = match.group(1) if match else None
            print(f"[CLASS] extracted = {class_num}")

            # ==================================================
            # 5️⃣ 밑줄 텍스트 정규화
            # ==================================================
            # - (underlined goods) 제거
            # - goods/services 처리
            # - class prefix 유지 여부 조정
            normalized_text = normalize_underlined_text(
                text,
                remove_class=False
            )

            print(f"[NORMALIZED TEXT] '{normalized_text}'")

            # ==================================================
            # 6️⃣ 제외 대상 텍스트 검사
            # ==================================================
            # Fax, Tel, Email, 심사관/팀장/국장 등
            excluded = should_exclude_underlined_text(normalized_text)
            print(f"[EXCLUDE CHECK] excluded={excluded}")

            # ==================================================
            # 7️⃣ 결과 저장
            # ==================================================
            if normalized_text and len(normalized_text) > 1 and not excluded:
                result_item = {
                    "page": page_num + 1,
                    "y": line["y"],
                    "text": normalized_text,
                    "class": class_num
                }

                print(f"[ADD RESULT] {result_item}")
                results.append(result_item)
            else:
                print("[SKIP] empty / excluded / too short")

    # ==================================================
    # 8️⃣ PDF 닫기
    # ==================================================
    doc.close()

    print("\n[END] extract_underlined_with_positions")
    print(f"[RESULT COUNT] {len(results)}")
    print(f"[RESULT DATA]\n{results}")

    return results

def match_underlines_to_sections(sections, underlines):
    """
    밑줄 데이터를 상표 섹션에 매칭하는 함수

    흐름:
    1. 상표 섹션(page_start ~ page_end, y_start ~ y_end) 순회
    2. 해당 섹션에 포함되는 밑줄 데이터만 필터링
    3. 세미콜론 기준 병합
    4. 최종 상품 단위로 분리
    """

    print("\n================ MATCH UNDERLINES TO SECTIONS ================\n")

    results = []

    # 1️⃣ 상표 섹션 단위 순회
    for s_idx, section in enumerate(sections, 1):
        print(f"\n[SECTION {s_idx}]")
        print(f"  page range : {section['page_start']} ~ {section['page_end']}")
        print(f"  y range    : {section['y_start']} ~ {section['y_end']}")

        section_underlines = []

        # 2️⃣ 모든 밑줄 데이터 순회
        for u_idx, u in enumerate(underlines, 1):
            print(f"\n  └─ [UNDERLINE {u_idx}] page={u['page']} y={u['y']} text='{u['text']}'")

            # 2-1️⃣ 페이지 범위 체크
            in_page_range = (
                section["page_start"] <= u["page"] <= section["page_end"]
            )

            if not in_page_range:
                print("     ❌ page range 불일치 → skip")
                continue

            # 2-2️⃣ 시작 페이지 y 범위 체크
            if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
                print("     ❌ start page y 범위 위 → skip")
                continue

            # 2-3️⃣ 종료 페이지 y 범위 체크
            if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
                print("     ❌ end page y 범위 아래 → skip")
                continue

            # 2-4️⃣ 조건 통과 → 섹션에 포함
            print("     ✅ section에 포함")
            section_underlines.append(u)

        print(f"\n  ▶ section_underlines ({len(section_underlines)}개):")
        for item in section_underlines:
            print(f"     - {item}")

        # 3️⃣ 병합 + 분리
        if section_underlines:
            print("\n  ▶ merge_by_semicolon 실행")
            merged = merge_by_semicolon(section_underlines)

            print("  ▶ merge 결과:")
            for m in merged:
                print(f"     - {m}")

            print("\n  ▶ split_products 실행")
            final_goods = split_products(merged)

            print("  ▶ split 결과:")
            for fg in final_goods:
                print(f"     - {fg}")

            # 4️⃣ 최종 goods 리스트 구성
            goods_list = []
            for item in final_goods:
                goods_text = item["text"].strip()
                class_num = item.get("class")

                goods_list.append({
                    "class": class_num,
                    "goods": goods_text
                })

        else:
            print("\n  ▶ section_underlines 없음")
            goods_list = []

        # 5️⃣ 섹션 결과 저장
        section_result = {
            "mark_number": section.get("mark_number"),
            "filing_number": section["filing_number"],
            "international_registration": section["international_registration"],
            "underlined_goods": goods_list
        }

        print("\n  ▶ SECTION RESULT:")
        print(section_result)

        results.append(section_result)

    print("\n================ MATCH END ================\n")
    return results

def normalize_underlined_text(text: str, remove_class: bool = False) -> str:
    """
    밑줄 텍스트를 정규화하는 함수
    - 불필요한 prefix 제거
    - goods/services 형태 보정
    - Class 제거 옵션 처리
    """

    print("\n[NORMALIZE START]")
    print(f"INPUT TEXT: '{text}'")
    print(f"remove_class = {remove_class}")

    # 1️⃣ 앞뒤 공백 제거
    text = text.strip()
    print(f"[STEP 1] strip -> '{text}'")

    # 2️⃣ 'all' 또는 'All' 단독인 경우 그대로 반환
    if re.fullmatch(r"(all|All)", text):
        print("[STEP 2] matched 'all' only → return 그대로")
        return text

    # 3️⃣ '(underlined goods)' 제거
    before = text
    text = re.sub(
        r"^\(\s*underlined goods\s*\)\s*",
        "",
        text,
        flags=re.IGNORECASE
    )
    if before != text:
        print(f"[STEP 3] remove '(underlined goods)' -> '{text}'")

    # 4️⃣ '(underlined goods/services)' 제거
    before = text
    text = re.sub(
        r"^\(\s*underlined goods/services\s*\)\s*",
        "",
        text,
        flags=re.IGNORECASE
    )
    if before != text:
        print(f"[STEP 4] remove '(underlined goods/services)' -> '{text}'")

    # 5️⃣ Class 제거 옵션
    if remove_class:
        before = text
        text = remove_class_prefix(text)
        if before != text:
            print(f"[STEP 5] remove class prefix -> '{text}'")

    # 6️⃣ goods/services 로 끝나는 경우 ; 보정
    if re.search(r"goods/services\s*$", text, re.IGNORECASE):
        print("[STEP 6] ends with 'goods/services'")
        if not text.rstrip().endswith((';', '.')):
            text = text.rstrip() + ";"
            print(f"         append ';' -> '{text}'")

    # 7️⃣ 최종 정리
    text = text.strip()
    print(f"[NORMALIZE END] RESULT = '{text}'")

    return text

def should_exclude_underlined_text(text: str) -> bool:
    """
    밑줄 텍스트가 '상품 정보가 아닌 경우' 제외하기 위한 판단 함수
    """

    print("\n[EXCLUDE CHECK START]")
    print(f"INPUT TEXT: '{text}'")

    stripped = text.strip()
    print(f"[STEP 1] stripped -> '{stripped}'")

    # 1️⃣ << ... >> 형태 (메타/주석)
    if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
        print("[EXCLUDE] matched << >> pattern")
        return True

    # 2️⃣ 연락처 관련 키워드 포함 여부
    if re.search(r"\b(Fax|Tel\.?|Telephone|E-mail|Email)\b", stripped, re.IGNORECASE):
        print("[EXCLUDE] contact keyword detected (Fax/Tel/Email)")
        return True

    # 3️⃣ 이메일 주소 포함
    if "@" in stripped:
        print("[EXCLUDE] '@' detected (email)")
        return True

    # 4️⃣ 심사관 직책 단독 텍스트
    if stripped in ["심사관 파트장 팀장 국장", "심사관 팀장 국장"]:
        print("[EXCLUDE] examiner title only")
        return True

    print("[KEEP] valid underlined text")
    return False

def merge_by_semicolon(results):
    """
    세미콜론(;) 또는 마침표(.) 기준으로 밑줄 텍스트를 병합하는 함수
    - 결과물에는 ; / . 을 제거하지 않고 그대로 유지
    - 페이지가 바뀌면 무조건 flush
    """

    print("\n================ MERGE BY SEMICOLON START ================\n")

    merged = []            # 최종 병합 결과 리스트
    current_text = ""      # 현재 누적 중인 텍스트
    current_page = None    # 현재 처리 중인 페이지
    current_class = None   # 현재 누적 중인 class

    # 1️⃣ underline 결과 하나씩 순회
    for idx, item in enumerate(results, 1):
        text = item["text"]
        page = item["page"]
        class_num = item.get("class")

        print(f"[{idx}] INPUT ITEM")
        print(f"    page  : {page}")
        print(f"    text  : '{text}'")
        print(f"    class : {class_num}")

        # 2️⃣ 직함/서명 관련 텍스트 제거
        if text in ['심사관', '파트장', '팀장', '국장', '팀장 국장']:
            print("    ❌ 직함 텍스트 → skip")
            continue

        # 3️⃣ 페이지 변경 감지 → 이전 누적 데이터 flush
        if current_page is not None and page != current_page:
            print("    🔄 페이지 변경 감지")

            if current_text:
                print(f"    ▶ flush (page={current_page}) : '{current_text}'")
                merged.append({
                    "page": current_page,
                    "text": current_text.strip(),  # ❗ 끝 문자 제거 안 함
                    "class": current_class
                })

                current_text = ""
                current_class = None

        # 현재 페이지 갱신
        current_page = page

        # 4️⃣ class 설정 (처음 한 번만)
        if class_num and not current_class:
            current_class = class_num
            print(f"    📌 class 설정: {current_class}")

        # 5️⃣ 텍스트 누적
        if current_text:
            current_text += " " + text
        else:
            current_text = text

        print(f"    ➕ 누적 텍스트: '{current_text}'")

        # 6️⃣ 병합 종료 조건 (; 또는 .)
        if current_text.rstrip().endswith(";") or current_text.rstrip().endswith("."):
            print("    ✅ 병합 종료 조건 충족 (; or .)")

            merged.append({
                "page": page,
                "text": current_text,  # ❗ 그대로 유지
                "class": current_class or class_num
            })

            print(f"    ▶ append: '{current_text}'")

            # 누적 상태 초기화
            current_text = ""
            current_class = None
            continue

    # 7️⃣ 루프 종료 후 잔여 데이터 처리
    if current_text:
        print("\n🧹 마지막 잔여 데이터 flush")
        print(f"    page={current_page}, text='{current_text}'")

        merged.append({
            "page": current_page,
            "text": current_text.strip(),
            "class": current_class
        })

    print("\n================ MERGE RESULT ================\n")
    for m in merged:
        print(m)

    print("\n================ MERGE END ================\n")
    return merged

def split_products(merged_results):
    """
    병합된 밑줄 텍스트를 실제 상품 단위로 분리하는 함수

    분리 규칙:
    1. 세미콜론(;)이 있으면 ; 기준 분리
    2. 세미콜론이 없고 콤마(,)가 있으면 , 기준 분리
    3. 구분자가 없으면 하나의 상품으로 처리
    """

    print("\n================ SPLIT PRODUCTS START ================\n")

    final_results = []

    # 1️⃣ 병합된 결과 하나씩 처리
    for idx, item in enumerate(merged_results, 1):
        page = item["page"]
        text = item["text"]
        class_num = item.get("class")

        print(f"[{idx}] INPUT MERGED ITEM")
        print(f"    page  : {page}")
        print(f"    text  : '{text}'")
        print(f"    class : {class_num}")

        # 2️⃣ [Class XX] 같은 접두어 제거
        text_without_class = remove_class_prefix(text)
        print(f"    after remove_class_prefix: '{text_without_class}'")

        # 3️⃣ 세미콜론 기준 분리
        if ";" in text_without_class:
            print("    🔹 split by ';'")
            parts = [
                p.strip().replace(".", "")
                for p in text_without_class.split(";")
                if p.strip()
            ]

        # 4️⃣ 세미콜론 없으면 콤마 기준 분리
        elif "," in text_without_class:
            print("    🔹 split by ','")
            parts = [
                p.strip().replace(".", "")
                for p in text_without_class.split(",")
                if p.strip()
            ]

        # 5️⃣ 구분자 자체가 없는 경우
        else:
            print("    🔹 no delimiter → single item")
            parts = [
                text_without_class.strip().replace(".", "")
            ]

        print(f"    ▶ split result parts: {parts}")

        # 6️⃣ 결과 누적
        for part in parts:
            final_item = {
                "page": page,
                "text": part,
                "class": class_num
            }
            print(f"    ➕ append final item: {final_item}")

            final_results.append(final_item)

    print("\n================ SPLIT PRODUCTS RESULT ================\n")
    for r in final_results:
        print(r)

    print("\n================ SPLIT PRODUCTS END ================\n")
    return final_results

def remove_class_prefix(text: str) -> str:
    """
    텍스트 앞에 붙은 [Class XX] 패턴을 제거하는 함수
    예:
      "[Class 10] Shampoos" → "Shampoos"
    """

    print(f"    🔧 remove_class_prefix input: '{text}'")

    cleaned = re.sub(
        r'\[Class\s+\d+\]\s*',  # [Class 10] 패턴
        '',
        text,
        flags=re.IGNORECASE
    ).strip()

    print(f"    🔧 remove_class_prefix output: '{cleaned}'")

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
    underlines = extract_underlined_with_positions(pdf_path)
    results = match_underlines_to_sections(sections, underlines)
    print(f"\n{results}\n")

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
