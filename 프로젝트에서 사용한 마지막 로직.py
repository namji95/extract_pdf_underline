# async def extract_underline(self, file_path: str, filename: str, trademark_es):
#     app_reference_number = filename.split("_")[0]
#     logger.info(f"app_reference_number: {app_reference_number} -> PDF UNDERLINE 추출 프로세스 시작.")
#
#     sections = self.extract_trademark_sections(file_path)
#     underlines_semicolon = self.extract_underlined_with_positions_semicolon(file_path)
#     underlines_only = self.extract_underlines_only(file_path)
#
#     logger.info(f"\nself.extract_underlined_with_positions_semicolon:\n{underlines_semicolon}\n")
#     logger.info(f"\nself.extract_underlines_only:\n{underlines_only}\n")
#
#     # underlines_only를 인자로 전달해야 함
#     tagged_results_comma = await self.extract_goods_with_spans_comma(
#         file_path, underlines_only, app_reference_number, trademark_es
#     )
#
#     final_results = []
#
#     for section in sections:
#         section_goods_text = ""
#
#         for u in underlines_semicolon:
#             if not (section["page_start"] <= u["page"] <= section["page_end"]):
#                 continue
#             if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
#                 continue
#             if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
#                 continue
#             section_goods_text += u.get("full_text", "") + " "
#
#         for tr in tagged_results_comma:
#             tr_page = tr["page"]
#             tr_y0 = tr["y0"]
#             if not (section["page_start"] <= tr_page <= section["page_end"]):
#                 continue
#             if tr_page == section["page_start"] and tr_y0 < section["y_start"]:
#                 continue
#             if tr_page == section["page_end"] and tr_y0 >= section["y_end"]:
#                 continue
#             section_goods_text += tr.get("text", "") + " "
#
#         logger.info(f"\nsection_goods_text:\n{section_goods_text}\n")
#         delimiter_type = self.detect_delimiter_for_goods_text(section_goods_text)
#         logger.info(f"\ndelimiter_typ:\n{delimiter_type}\n")
#
#         if delimiter_type == 'semicolon':
#             section_underlines = []
#             for u in underlines_semicolon:
#                 if not (section["page_start"] <= u["page"] <= section["page_end"]):
#                     continue
#                 if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
#                     continue
#                 if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
#                     continue
#                 section_underlines.append(u)
#
#             result = self.match_underlines_to_sections_semicolon([section], section_underlines)
#             if result and result[0].get("underlined_goods"):
#                 for goods_item in result[0]["underlined_goods"]:
#                     final_results.append({
#                         "filing_number": section["filing_number"],
#                         "international_registration_number": section["international_registration"],
#                         "class": goods_item.get("class"),
#                         "goods": goods_item.get("goods")
#                     })
#         else:
#             # comma 구분자 처리
#             matched_list = []
#             for tr in tagged_results_comma:
#                 tr_page = tr["page"]
#                 tr_y0 = tr["y0"]
#
#                 if not (section["page_start"] <= tr_page <= section["page_end"]):
#                     continue
#                 if tr_page == section["page_start"] and tr_y0 < section["y_start"]:
#                     continue
#                 if tr_page == section["page_end"] and tr_y0 >= section["y_end"]:
#                     continue
#
#                 matched_list.append(tr)
#
#             for item in matched_list:
#                 is_single_data = item.get("is_single_data", False)
#                 tagged_text = item.get("tagged_text", "")
#
#                 if is_single_data:
#                     # ES 조회 결과 True: 병합된 상태로 밑줄 부분에만 <u> 태그 적용
#                     # tagged_text는 이미 apply_underline_tags로 밑줄 부분에 <u> 태그가 적용된 상태
#                     final_results.append({
#                         "filing_number": section["filing_number"],
#                         "international_registration_number": section["international_registration"],
#                         "class": item.get("class"),
#                         "goods": self.clean_goods_text(tagged_text)
#                     })
#                 else:
#                     # ES 조회 결과 False: 쉼표 기준으로 분할 후 밑줄 부분만 추출
#                     goods = self.extract_goods_from_tagged_text(tagged_text)
#                     for g in goods:
#                         final_results.append({
#                             "filing_number": section["filing_number"],
#                             "international_registration_number": section["international_registration"],
#                             "class": item.get("class"),
#                             "goods": self.clean_goods_text(g)
#                         })
#
#     for f in final_results:
#         print(json.dumps(f, indent=2, ensure_ascii=False))
#
#     return final_results
#
#
# def filter_results_by_stop_patterns(self, results: list) -> list:
#     """
#     '※ Note' 또는 '10. Guidance' 패턴이 포함된 항목 이후의 모든 데이터를 제거
#     """
#     logger.info(f'\n\n{results}\n\n')
#     stop_patterns = [
#         r'※\s*Note',
#         r'10\.\s*Guidance\s*(for the response)?\s*:?'
#     ]
#
#     filtered = []
#     for item in results:
#         goods = item.get("goods", "")
#         # 태그 제거 후 체크
#         text_only = re.sub(r'</?u>', '', goods)
#
#         should_stop = False
#         for pattern in stop_patterns:
#             if re.search(pattern, text_only, re.IGNORECASE):
#                 should_stop = True
#                 break
#
#         if should_stop:
#             break  # 이후 데이터 모두 무시
#
#         filtered.append(item)
#
#     return filtered
#
#
# def extract_trademark_sections(self, pdf_path):
#     doc = fitz.open(pdf_path)
#     sections = []
#     all_blocks = []
#
#     for page_num, page in enumerate(doc):
#         blocks = page.get_text("dict")["blocks"]
#
#         for block in blocks:
#             if "lines" not in block:
#                 continue
#
#             block_text = ""
#             for line in block["lines"]:
#                 for span in line["spans"]:
#                     block_text += span["text"] + " "
#
#             block_text = block_text.strip()
#
#             block_info = {
#                 "page": page_num + 1,
#                 "y0": block["bbox"][1],
#                 "y1": block["bbox"][3],
#                 "text": block_text
#             }
#
#             all_blocks.append(block_info)
#
#     section_starts = []
#
#     for idx, block in enumerate(all_blocks):
#         text = block["text"]
#         text_cleaned = text.replace("□", "").replace("☐", "").strip()
#
#         match = re.search(
#             r"Information\s+concerning\s+the\s+earlier\s+mark\s*\((\d+)\)",
#             text_cleaned,
#             re.IGNORECASE
#         )
#
#         if match:
#             mark_number = int(match.group(1))
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": mark_number,
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#             continue
#
#         match = re.search(
#             r"Information\s+concerning\s+the\s+earlier\s+mark\s*$",
#             text_cleaned,
#             re.IGNORECASE
#         )
#
#         if match:
#             section_starts.append({
#                 "index": idx,
#                 "mark_number": 1,
#                 "page": block["page"],
#                 "y": block["y0"]
#             })
#
#     if not section_starts:
#         doc.close()
#
#         return [{
#             "mark_number": 1,
#             "filing_number": None,
#             "international_registration": None,
#             "page_start": 1,
#             "page_end": all_blocks[-1]["page"] if all_blocks else 1,
#             "y_start": 0,
#             "y_end": float('inf')
#         }]
#
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
#         section_text = " ".join(
#             all_blocks[j]["text"] for j in range(start["index"], end_idx)
#         )
#
#         filing_match = re.search(r"Filing\s+number\s*:\s*(\d+)", section_text)
#         filing_number = filing_match.group(1) if filing_match else None
#
#         ir_match = re.search(
#             r"International\s+registration\s+number\s*:\s*(\d+)",
#             section_text,
#             re.IGNORECASE
#         )
#         international_registration = ir_match.group(1) if ir_match else None
#
#         sections.append({
#             "mark_number": start["mark_number"],
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
# def find_rect_regions(self, page):
#     drawings = page.get_drawings()
#     rects = []
#
#     for d in drawings:
#         items = d.get("items", [])
#
#         for item in items:
#             if item[0] == "re":
#                 rect = item[1]
#                 if rect.width > 50 and rect.height > 20:
#                     rects.append(rect)
#
#         if len(items) >= 4:
#             h_lines = []
#             v_lines = []
#
#             for item in items:
#                 if item[0] == "l":
#                     p1, p2 = item[1], item[2]
#                     if abs(p1.y - p2.y) < 2:
#                         h_lines.append((min(p1.x, p2.x), max(p1.x, p2.x), p1.y))
#                     elif abs(p1.x - p2.x) < 2:
#                         v_lines.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))
#
#             if len(h_lines) >= 2 and len(v_lines) >= 2:
#                 x_min = min(l[0] for l in h_lines)
#                 x_max = max(l[1] for l in h_lines)
#                 y_min = min(l[2] for l in h_lines)
#                 y_max = max(l[2] for l in h_lines)
#
#                 if (x_max - x_min) > 50 and (y_max - y_min) > 20:
#                     rects.append(fitz.Rect(x_min, y_min, x_max, y_max))
#
#     return rects
#
#
# def is_inside_rect(self, line, rects, margin=5):
#     line_y = line["y"]
#
#     for rect in rects:
#         if rect.y0 - margin <= line_y <= rect.y1 + margin:
#             return True
#
#     return False
#
#
# def extract_underlined_with_positions_semicolon(self, pdf_path):
#     doc = fitz.open(pdf_path)
#     results = []
#     last_class = None
#
#     # 데이터 추출 중단 패턴
#     STOP_PATTERNS = [
#         re.compile(r'※\s*Note', re.IGNORECASE),
#         re.compile(r'10\.\s*Guidance\s*(for the response)?\s*:?', re.IGNORECASE)
#     ]
#
#     def should_stop_extraction(text: str) -> bool:
#         """※ Note 또는 10. Guidance 패턴 체크"""
#         for pattern in STOP_PATTERNS:
#             if pattern.search(text):
#                 return True
#         return False
#
#     extraction_stopped = False
#
#     for page_num, page in enumerate(doc):
#         if extraction_stopped:
#             break
#         drawings = page.get_drawings()
#         lines = []
#
#         rect_regions = self.find_rect_regions(page)
#
#         for d in drawings:
#             for item in d.get("items", []):
#                 if item[0] == "l":
#                     p1, p2 = item[1], item[2]
#
#                     if abs(p1.y - p2.y) < 2:
#                         length = abs(p2.x - p1.x)
#
#                         if 10 < length < 500:
#                             line_info = {
#                                 "y": p1.y,
#                                 "x0": min(p1.x, p2.x),
#                                 "x1": max(p1.x, p2.x),
#                             }
#
#                             if not self.is_inside_rect(line_info, rect_regions):
#                                 lines.append(line_info)
#
#         lines = sorted(lines, key=lambda x: x["y"])
#
#         for line in lines:
#             anchor_rect = fitz.Rect(
#                 line["x0"] - 1,
#                 line["y"] - 12,
#                 line["x1"] + 1,
#                 line["y"] + 1,
#             )
#
#             raw_text = page.get_text("text", clip=anchor_rect)
#             if raw_text.startswith(('심사관', '파트장', '팀장', '국장')):
#                 continue
#
#             anchor_text = " ".join(raw_text.strip().split())
#
#             if not anchor_text:
#                 continue
#
#             full_rect = fitz.Rect(
#                 0,
#                 line["y"] - 12,
#                 page.rect.width,
#                 line["y"] + 1,
#             )
#
#             full_raw_text = page.get_text("text", clip=full_rect)
#             full_text = " ".join(full_raw_text.strip().split())
#
#             if not full_text:
#                 continue
#
#             # ※ Note 또는 10. Guidance 패턴 체크 - 발견 시 추출 중단
#             if should_stop_extraction(full_text):
#                 logger.info(f"Stop 패턴 발견으로 데이터 추출 중단: {full_text[:100]}...")
#                 extraction_stopped = True
#                 break
#
#             match = re.search(r'\[Class\s+(\d+)\]', full_text, re.IGNORECASE)
#             class_num = match.group(1) if match else None
#
#             if not class_num:
#                 extended_rect = fitz.Rect(
#                     0,
#                     line["y"] - 30,
#                     page.rect.width,
#                     line["y"] + 1,
#                 )
#                 extended_text = page.get_text("text", clip=extended_rect)
#                 extended_text = " ".join(extended_text.strip().split())
#                 match = re.search(r'\[Class\s+(\d+)\]', extended_text, re.IGNORECASE)
#                 class_num = match.group(1) if match else None
#
#             if class_num:
#                 last_class = class_num
#             else:
#                 class_num = last_class
#
#             normalized_text = self.normalize_for_compare(anchor_text)
#
#             if self.should_exclude_underlined_text(normalized_text):
#                 continue
#
#             underline_core = re.sub(r"[.]\s*$", "", normalized_text).strip()
#
#             if not underline_core:
#                 continue
#
#             tagged_text = f"<u>{underline_core}</u>"
#
#             result_item = {
#                 "page": page_num + 1,
#                 "y": line["y"],
#                 "text": underline_core,
#                 "full_text": full_text,
#                 "tagged_text": tagged_text,
#                 "class": class_num,
#             }
#
#             results.append(result_item)
#
#     doc.close()
#     return results
#
#
# def extract_underlines_only(self, pdf_path):
#     doc = fitz.open(pdf_path)
#     underlines = []
#
#     for page_num, page in enumerate(doc):
#         drawings = page.get_drawings()
#
#         for d in drawings:
#             for item in d.get("items", []):
#                 if item[0] == "l":
#                     p1, p2 = item[1], item[2]
#
#                     if abs(p1.y - p2.y) < 2:
#                         length = abs(p2.x - p1.x)
#
#                         if 10 < length < 500:
#                             clip_rect = fitz.Rect(
#                                 min(p1.x, p2.x) - 1,
#                                 p1.y - 12,
#                                 max(p1.x, p2.x) + 1,
#                                 p1.y + 1
#                             )
#                             text = page.get_text("text", clip=clip_rect).strip()
#                             text = " ".join(text.split())
#                             text = text.rstrip(',;.')
#
#                             underlines.append({
#                                 "page": page_num + 1,
#                                 "y": p1.y,
#                                 "x0": min(p1.x, p2.x),
#                                 "x1": max(p1.x, p2.x),
#                                 "text": text,
#                             })
#
#     doc.close()
#     return underlines
#
#
# async def extract_goods_with_spans_comma(self, pdf_path, underlines, app_reference_number, trademark_es):
#     doc = fitz.open(pdf_path)
#     results = []
#
#     ANCHOR_PATTERN = re.compile(
#         r"Goods(?:/Services)?\s+of\s+the\s+(?:applied[- ]for|proposed)\s+mark",
#         re.IGNORECASE
#     )
#
#     PAGE_NUM_PATTERN = re.compile(r'^\s*-\s*\d+\s*-\s*$')
#
#     ALL_DESIGNATED_PATTERN = re.compile(
#         r'[\'\""\']?\s*all\s*[\'\""\']?\s+the\s+designated\s+(goods\s*/\s*services|goods|services)',
#         re.IGNORECASE
#     )
#
#     # 데이터 추출 중단 패턴
#     STOP_PATTERNS = [
#         re.compile(r'※\s*Note', re.IGNORECASE),
#         re.compile(r'10\.\s*Guidance\s*(for the response)?\s*:?', re.IGNORECASE)
#     ]
#
#     def should_stop_extraction(text: str) -> bool:
#         """※ Note 또는 10. Guidance 패턴 체크"""
#         for pattern in STOP_PATTERNS:
#             if pattern.search(text):
#                 return True
#         return False
#
#     def get_underlined_texts_for_page(page, page_num):
#         """페이지에서 밑줄 바로 위의 텍스트 추출"""
#         underlined_texts = []
#         page_underlines = [ul for ul in underlines if ul["page"] == page_num]
#
#         for ul in page_underlines:
#             clip_rect = fitz.Rect(
#                 ul["x0"] - 1,
#                 ul["y"] - 12,
#                 ul["x1"] + 1,
#                 ul["y"] + 1
#             )
#             text = page.get_text("text", clip=clip_rect).strip()
#             text = " ".join(text.split())
#
#             text = text.rstrip(',;.')
#
#             if text:
#                 if self.should_exclude_underlined_text(text):
#                     continue
#
#                 underlined_texts.append({
#                     "text": text,
#                     "y": ul["y"],
#                     "x0": ul["x0"],
#                     "x1": ul["x1"]
#                 })
#
#         return underlined_texts
#
#     def apply_underline_tags(full_text, underlined_texts):
#         """전체 텍스트에서 밑줄 텍스트에만 <u> 태그 적용"""
#         if not underlined_texts:
#             return full_text
#
#         tagged_text = full_text
#
#         sorted_ul_texts = sorted(underlined_texts, key=lambda x: len(x["text"]), reverse=True)
#
#         for ul in sorted_ul_texts:
#             ul_text = ul["text"]
#             if not ul_text:
#                 continue
#
#             if f"<u>{ul_text}</u>" in tagged_text:
#                 continue
#
#             if ul_text in tagged_text:
#                 pattern = re.compile(re.escape(ul_text))
#                 matches = list(pattern.finditer(tagged_text))
#
#                 # 앞에서부터 매칭 (밑줄은 보통 첫 번째 출현에 있음)
#                 for match in matches:
#                     start, end = match.start(), match.end()
#
#                     before = tagged_text[:start]
#                     if before.count("<u>") > before.count("</u>"):
#                         continue
#
#                     tagged_text = tagged_text[:start] + f"<u>{ul_text}</u>" + tagged_text[end:]
#                     break
#
#         return tagged_text
#
#     buffer_texts = []
#     buffer_page = None
#     buffer_y0 = float('inf')
#     buffer_y1 = 0
#     buffer_underlined_texts = []
#     buffer_class = None
#     last_class = None
#     extraction_stopped = False  # 추출 중단 플래그
#
#     async def flush_buffer():
#         nonlocal buffer_texts, buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts, buffer_class, last_class, extraction_stopped
#
#         if not buffer_texts:
#             return False
#
#         full_text = " ".join(buffer_texts)
#         full_text = re.sub(r'\s+', ' ', full_text).strip()
#
#         # ※ Note 또는 10. Guidance 패턴 체크 - 발견 시 추출 중단
#         if should_stop_extraction(full_text):
#             logger.info(f"Stop 패턴 발견으로 데이터 추출 중단: {full_text[:100]}...")
#             extraction_stopped = True
#             buffer_texts = []
#             buffer_y0 = float('inf')
#             buffer_y1 = 0
#             buffer_underlined_texts = []
#             buffer_class = None
#             return True  # 추출 중단 신호
#
#         es_result = await trademark_es.check_international_trademark_data(
#             app_reference_number=app_reference_number, goods=full_text
#         )
#         logger.info(f"comma 데이터 ES 조회 결과: {es_result}")
#
#         if full_text:
#             tagged_text = apply_underline_tags(full_text, buffer_underlined_texts)
#
#             class_match = re.search(r'\[Class\s+(\d+)\]', full_text, re.IGNORECASE)
#             if class_match:
#                 class_num = class_match.group(1)
#                 last_class = class_num
#             elif buffer_class:
#                 class_num = buffer_class
#             else:
#                 class_num = last_class
#
#             results.append({
#                 "page": buffer_page,
#                 "text": full_text,
#                 "tagged_text": tagged_text,
#                 "y0": buffer_y0,
#                 "y1": buffer_y1,
#                 "class": class_num,
#                 "is_single_data": es_result,
#             })
#
#         buffer_texts = []
#         buffer_y0 = float('inf')
#         buffer_y1 = 0
#         buffer_underlined_texts = []
#         buffer_class = None
#         return False
#
#     def add_to_buffer(text, y0, y1, page, page_underlined_texts):
#         nonlocal buffer_page, buffer_y0, buffer_y1, buffer_underlined_texts, buffer_class, last_class
#
#         buffer_texts.append(text)
#         buffer_page = page
#         buffer_y0 = min(buffer_y0, y0)
#         buffer_y1 = max(buffer_y1, y1)
#
#         # [Class XX] 추출
#         class_match = re.search(r'\[Class\s+(\d+)\]', text, re.IGNORECASE)
#         if class_match:
#             buffer_class = class_match.group(1)
#             last_class = buffer_class  # 마지막 class 값 업데이트
#
#         for ul in page_underlined_texts:
#             if y0 - 5 <= ul["y"] <= y1 + 5:
#                 if ul not in buffer_underlined_texts:
#                     buffer_underlined_texts.append(ul)
#
#     after_anchor = False
#
#     for page_num, page in enumerate(doc):
#         if extraction_stopped:
#             break
#
#         text_dict = page.get_text("dict")
#         page_underlined_texts = get_underlined_texts_for_page(page, page_num + 1)
#
#         for block in text_dict["blocks"]:
#             if extraction_stopped:
#                 break
#
#             if "lines" not in block:
#                 continue
#
#             for line_obj in block["lines"]:
#                 if extraction_stopped:
#                     break
#
#                 for span in line_obj["spans"]:
#                     if extraction_stopped:
#                         break
#
#                     txt = span["text"]
#                     bbox = span["bbox"]
#
#                     if not txt.strip():
#                         continue
#
#                     if PAGE_NUM_PATTERN.match(txt.strip()):
#                         continue
#
#                     if ANCHOR_PATTERN.search(txt):
#                         after_anchor = True
#                         colon_idx = txt.find(":")
#                         if colon_idx != -1 and colon_idx < len(txt) - 1:
#                             after_colon = txt[colon_idx + 1:].strip()
#                             if after_colon:
#                                 if '.' in after_colon:
#                                     parts = re.split(r'([.])', after_colon)
#                                     for part in parts:
#                                         if extraction_stopped:
#                                             break
#                                         if not part:
#                                             continue
#                                         if part == '.':
#                                             if await flush_buffer():
#                                                 break
#                                             after_anchor = False
#                                         else:
#                                             add_to_buffer(part, bbox[1], bbox[3], page_num + 1,
#                                                           page_underlined_texts)
#                                 else:
#                                     add_to_buffer(after_colon, bbox[1], bbox[3], page_num + 1,
#                                                   page_underlined_texts)
#                                     # "all the designated" 패턴 체크 - ':'뒤에 바로 있는 경우
#                                     current_buffer_text = " ".join(buffer_texts)
#                                     if ALL_DESIGNATED_PATTERN.search(current_buffer_text):
#                                         if await flush_buffer():
#                                             break
#                                         after_anchor = False
#                         continue
#
#                     if not after_anchor:
#                         continue
#
#                     # '.'으로만 분리 (','는 분리 안함)
#                     if '.' in txt:
#                         parts = re.split(r'([.])', txt)
#                         for part in parts:
#                             if extraction_stopped:
#                                 break
#                             if not part:
#                                 continue
#                             if part == '.':
#                                 if await flush_buffer():
#                                     break
#                                 after_anchor = False
#                             else:
#                                 add_to_buffer(part, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
#                     else:
#                         add_to_buffer(txt, bbox[1], bbox[3], page_num + 1, page_underlined_texts)
#
#                     if extraction_stopped:
#                         break
#
#                     # "all the designated goods/services" 패턴 체크 - '.'이 없어도 flush
#                     current_buffer_text = " ".join(buffer_texts)
#                     if ALL_DESIGNATED_PATTERN.search(current_buffer_text):
#                         if await flush_buffer():
#                             break
#                         after_anchor = False
#
#     if not extraction_stopped:
#         await flush_buffer()
#     doc.close()
#     return results
#
#
# def detect_delimiter_for_goods_text(self, goods_text):
#     """
#     특정 Goods/Services 텍스트의 구분자 타입 판단
#     - ';'가 있으면 'semicolon' 반환
#     - ';'가 없으면 'comma' 반환
#     """
#     if ';' in goods_text:
#         return 'semicolon'
#     return 'comma'
#
#
# def match_underlines_to_sections_semicolon(self, sections, underlines):
#     results = []
#
#     for section in sections:
#         goods_list = []
#
#         section_underlines = []
#         for u in underlines:
#             if not (section["page_start"] <= u["page"] <= section["page_end"]):
#                 continue
#             if u["page"] == section["page_start"] and u["y"] < section["y_start"]:
#                 continue
#             if u["page"] == section["page_end"] and u["y"] >= section["y_end"]:
#                 continue
#
#             section_underlines.append(u)
#
#         section_underlines = self.merge_multiline_underlines(section_underlines)
#
#         for u in section_underlines:
#             ALL_DESIGNATED_PATTERN = re.compile(
#                 r'(?i)[\'\""\"]?\s*all\s*[\'\""\"]?\s+the\s+designated\s+(goods\s*/\s*services|goods|services)',
#                 re.VERBOSE
#             )
#             if ALL_DESIGNATED_PATTERN.search(u.get("full_text", "")):
#                 g = "<u>all the designated goods/services</u>"
#                 goods_list.append({
#                     "class": u.get("class"),
#                     "goods": g
#                 })
#                 continue
#
#             goods = self.extract_goods_from_tagged_text(u["tagged_text"])
#             full_text = u.get("full_text", "")
#             # ; 이 있으면 ; 로만 분리, 없으면 , 로 분리
#             if ';' in full_text:
#                 full_goods_parts = [
#                     p.strip()
#                     for p in re.split(r"[;.]", full_text)
#                     if p.strip()
#                 ]
#             else:
#                 full_goods_parts = [
#                     p.strip()
#                     for p in re.split(r"[,.]", full_text)
#                     if p.strip()
#                 ]
#
#             for g in goods:
#                 core = re.sub(r"</?u>", "", g).strip()
#
#                 extended = None
#                 standalone_exists = any(
#                     p.strip().lower() == core.lower()
#                     for p in full_goods_parts
#                 )
#
#                 for part in full_goods_parts:
#                     if (
#                             part.lower().startswith(core.lower() + " ")
#                             and not standalone_exists
#                     ):
#                         extended = part
#                         break
#
#                 if extended:
#                     goods_list.append({
#                         "class": u.get("class"),
#                         "goods": extended.replace(
#                             core,
#                             f"<u>{core}</u>",
#                             1
#                         )
#                     })
#                 else:
#                     goods_list.append({
#                         "class": u.get("class"),
#                         "goods": g
#                     })
#
#         results.append({
#             "mark_number": section.get("mark_number"),
#             "filing_number": section["filing_number"],
#             "international_registration": section["international_registration"],
#             "underlined_goods": goods_list
#         })
#
#     for r in results:
#         for item in r["underlined_goods"]:
#             item["goods"] = self.clean_goods_text(item["goods"])
#
#     return results
#
#
# def clean_goods_text(self, goods: str) -> str:
#     if not goods:
#         return goods
#
#     goods = re.sub(
#         r"^\*?\s*Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground:\s*",
#         "",
#         goods,
#         flags=re.IGNORECASE
#     )
#
#     goods = re.sub(r"\s*\[\s*Class\s*\d+\s*\]\s*", "", goods, flags=re.IGNORECASE)
#     goods = re.sub(r"<u>\s+", "<u>", goods)
#     goods = re.sub(r"\s{2,}", " ", goods)
#
#     return goods.strip()
#
#
# def normalize_for_compare(self, text: str) -> str:
#     if not text:
#         return ""
#
#     text = re.sub(
#         r"^\*?\s*Goods/Services\s+of\s+the\s+applied[- ]for\s+mark\s+in\s+relation\s+to\s+this\s+ground:\s*",
#         "",
#         text,
#         flags=re.IGNORECASE
#     )
#
#     text = re.sub(r"\[\s*Class\s*\d+\s*\]", "", text, flags=re.IGNORECASE)
#     text = re.sub(r"\s{2,}", " ", text)
#
#     return text.strip()
#
#
# def should_exclude_underlined_text(self, text: str) -> bool:
#     stripped = text.strip()
#
#     if re.fullmatch(r"<<\s*[^<>]+\s*>>", stripped):
#         return True
#
#     if stripped.startswith("<<"):
#         return True
#
#     if "→" in stripped:
#         return True
#
#     if re.search(r"\b(Fax|Tel\.?|Telephone|E-mail|Email)\b", stripped, re.IGNORECASE):
#         return True
#
#     if "@" in stripped:
#         return True
#
#     if stripped in ["심사관 파트장 팀장 국장", "심사관 팀장 국장"]:
#         return True
#
#     if stripped.startswith(('심사관', '파트장', '팀장', '국장')):
#         return True
#
#     if re.search(r"underlined goods", stripped, re.IGNORECASE):
#         return True
#
#     if re.search(r"Ministry of Intellectual Property|MOIP", stripped, re.IGNORECASE):
#         return True
#
#     if re.search(r"<<\s*Information\s*>>", stripped, re.IGNORECASE):
#         return True
#
#     return False
#
#
# def merge_multiline_underlines(self, underlines, y_gap=20):
#     underlines = sorted(underlines, key=lambda x: (x["page"], x["y"]))
#     merged = []
#
#     ALL_DESIGNATED_PATTERN = re.compile(
#         r'[\'\""\']?\s*all\s*[\'\""\']?\s+the\s+designated\s+(goods\s*/\s*services|goods|services)',
#         re.IGNORECASE
#     )
#
#     buffer = None
#
#     for u in underlines:
#         if buffer is None:
#             buffer = u.copy()
#             continue
#
#         same_page = buffer["page"] == u["page"]
#         close_y = abs(u["y"] - buffer["y"]) < y_gap
#
#         text_strip = buffer["text"].strip()
#         if ';' in text_strip:
#             no_end = not text_strip.endswith((';', '.'))
#         else:
#             no_end = not text_strip.endswith((';', '.', ','))
#
#         is_all_designated = ALL_DESIGNATED_PATTERN.search(buffer["text"])
#
#         if same_page and close_y and no_end and not is_all_designated:
#             buffer["text"] = buffer["text"].rstrip(';') + " " + u["text"].lstrip()
#
#             buffer["tagged_text"] = (
#                     buffer["tagged_text"].replace("</u>", "") +
#                     " " +
#                     u["tagged_text"].replace("<u>", "")
#             )
#
#             buffer["y"] = u["y"]
#         else:
#             merged.append(buffer)
#             buffer = u.copy()
#
#     if buffer:
#         merged.append(buffer)
#
#     return merged
#
#
# def extract_goods_from_tagged_text(self, tagged_text: str) -> list:
#     goods = []
#
#     # 줄바꿈을 공백으로 치환하고 다중 공백을 단일 공백으로 정리
#     normalized_text = re.sub(r'\s+', ' ', tagged_text).strip()
#
#     # <u> 태그 안의 콤마/세미콜론을 임시 토큰으로 치환 (분할 기준에서 제외)
#     temp_comma = "<<COMMA>>"
#     temp_semicolon = "<<SEMICOLON>>"
#
#     def replace_delimiters_in_tags(m):
#         content = m.group(1)
#         content = content.replace(',', temp_comma)
#         content = content.replace(';', temp_semicolon)
#         return f"<u>{content}</u>"
#
#     normalized_text = re.sub(r"<u>(.*?)</u>", replace_delimiters_in_tags, normalized_text, flags=re.DOTALL)
#
#     # 전체 텍스트를 세미콜론이나 콤마로 분할
#     if ';' in normalized_text:
#         parts = [p.strip() for p in re.split(r";", normalized_text) if p.strip()]
#     else:
#         parts = [p.strip() for p in re.split(r",", normalized_text) if p.strip()]
#
#     # 각 분할된 부분에서 <u> 태그가 있는 부분만 추출
#     for part in parts:
#         # 임시 토큰 복원
#         part = part.replace(temp_comma, ",").replace(temp_semicolon, ";")
#
#         # <u> 태그가 있는 경우에만 처리 (밑줄 데이터만 추출)
#         if '<u>' in part and '</u>' in part:
#             # <u> 태그 안의 텍스트만 추출하여 합침
#             underline_texts = re.findall(r"<u>(.*?)</u>", part, re.DOTALL)
#             combined_text = ' '.join(underline_texts)
#             combined_text = re.sub(r'\s+', ' ', combined_text).strip()
#             if combined_text:
#                 goods.append(f"<u>{combined_text}</u>")
#
#     return goods