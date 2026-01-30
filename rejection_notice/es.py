from typing import Optional, Dict, List, Callable, Any

from elasticsearch.dsl import AsyncSearch, Q
from loguru import logger

from model import PaginatedResult, PaginationInfo


def format_number(value: str) -> str:
    """
    숫자 문자열을 특허청 형식에 맞게 포맷팅합니다.

    Args:
        value: 포맷팅할 숫자 문자열

    Returns:
        포맷팅된 문자열
        - 15자리: 확장 등록번호 (9052025088318023 -> 9-5-2025-0883180-23)
        - 13자리: 출원번호 (4020240012345 -> 40-2024-0012345)
        - 12자리: 특허고객번호 (120000429446 -> 1-2000-0429446-4)
        - 10자리: 등록번호 (9052025088 -> 9-5-2025-088)
        - 8자리: 대리인번호 (20240001 -> 2024-0001)
    """
    if not value or not value.isdigit():
        return value

    match len(value):
        case 15:  # 확장 등록번호
            return f"{value[0]}-{value[1]}-{value[2:6]}-{value[6:13]}-{value[13:]}"
        case 13:  # 출원번호
            return f"{value[:2]}-{value[2:6]}-{value[6:]}"
        case 12:  # 특허고객번호
            return f"{value[0]}-{value[1:5]}-{value[5:11]}-{value[11]}"
        case 11:
            return f"{value[0:4]}-{value[4:10]}-{value[10]}"
        case 10:  # 등록번호
            return f"{value[0]}-{value[1]}-{value[2:6]}-{value[6:]}"
        case 8:  # 대리인번호
            return f"{value[:4]}-{value[4:]}"
        case _:  # 그 외는 그대로 반환
            return value


class TrademarkEsRepository:
    ALIAS = 'trademark'

    def __init__(self, index_name: Optional[str] = None, alias: Optional[str] = None):
        self.INDEX_NAME = index_name or self.INDEX_NAME
        self.ALIAS = alias or self.ALIAS

        if not self.INDEX_NAME:
            raise ValueError("인덱스명이 반드시 설정되어 있어야 합니다.")
        if not self.ALIAS:
            raise ValueError("별칭이 반드시 설정되어 있어야 합니다.")

    async def search_application_sources(
            self,
            mark_name: Optional[str] = None,
            application_number: Optional[str] = None,
            reg_number: Optional[str] = None,
            goods_name: Optional[str] = None,
            applicant_name: Optional[str] = None,
            agent_name: Optional[str] = None,
            patent_customer_number: Optional[str] = None,
            goods_class: Optional[str] = None,
            agent_number: Optional[str] = None,
            page: int = 1,
            limit: int = 5
    ) -> PaginatedResult[dict]:
        """상표 출원서 검색 (모든 조건 AND)"""
        try:
            s = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)

            must = []

            # 1. 완전일치 필터 (must)
            if application_number:
                must.append(Q('term', application_number=application_number))

            if reg_number:
                must.append(Q('term', reg_number=reg_number))

            if patent_customer_number:
                must.append(
                    Q('nested',
                      path='applicants',
                      query=Q('term', **{"applicants.customer_code": patent_customer_number}))
                )

            if goods_class and goods_class.isdigit():
                original_len = len(goods_class)
                max_len = max(2, original_len, 3)  # 최소 2자리, 최대 3자리 확장
                zfill_candidates = list({goods_class.zfill(i) for i in range(original_len, max_len + 1)})

                base_query = Q(
                    'nested',
                    path='products',
                    query=Q('term', **{"products.main_code": goods_class})
                )

                if len(zfill_candidates) > 1:
                    # 원본과 zfill 후보들을 모두 OR 조건으로 묶기
                    should_queries = [
                        Q('nested', path='products', query=Q('term', **{"products.main_code": candidate}))
                        for candidate in zfill_candidates
                    ]
                    must.append(Q('bool', should=should_queries, minimum_should_match=1))
                else:
                    must.append(base_query)

            if agent_number:
                must.append(
                    Q('nested',
                      path='agents',
                      query=Q('term', **{"agents.customer_code": agent_number}))
                )

            # 2. 텍스트 검색 (must - 매치되는 게 있으면)
            if mark_name:
                queries = self._build_mark_name_query(mark_name)
                must.append(
                    Q('bool', should=queries, minimum_should_match=1)
                )

            if goods_name:
                must.append(
                    Q('nested',
                      path='products',
                      query=Q('bool',
                              should=[
                                  Q("wildcard", **{"products.designated_goods_kor": f"*{goods_name}*"}),
                                  Q("wildcard", **{"products.designated_goods_eng": f"*{goods_name}*"})
                              ],
                              minimum_should_match=1))
                )

            # 부분일치를 위한 wildcard 쿼리 사용
            if applicant_name:
                must.append(
                    Q('nested',
                      path='applicants',
                      query=Q('wildcard', **{"applicants.customer_kor_name": f"*{applicant_name}*"}))
                )

            if agent_name:
                must.append(
                    Q('nested',
                      path='agents',
                      query=Q('wildcard', **{"agents.customer_kor_name": f"*{agent_name}*"}))
                )

            # 3. Bool 쿼리 생성 (모든 조건이 must)
            if must:
                s = s.query(Q('bool', must=must))

            # 4. 정렬
            s = s.sort(
                {'_score': {'order': 'desc'}},
                {'application_date': {'order': 'desc'}}
            )

            # 5. 페이지네이션
            offset = (page - 1) * limit
            response = await s[offset:offset + limit].execute()
            total_count = response.hits.total.value

            self._logging_es_query(s)

            return PaginatedResult(
                items=self._format_hits(response),
                pagination=PaginationInfo(
                    limit=limit,
                    offset=offset + 1,
                    total_count=total_count,
                    total_pages=(total_count + limit - 1) // limit,
                    page=page
                )
            )
        except Exception as e:
            logger.exception("상표 검색 실패")
            raise

    async def search_application_source_by_application_number(
            self,
            application_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        상표 출원번호로 상세 정보를 조회합니다.
        """
        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", application_number=application_number)
        response = await search.execute()

        if not response.hits:
            from src.module.bases.exceptions import EntityNotFoundError
            logger.debug(f"출원번호({application_number})에 일치하는 정보가 조회되지 않음")
            raise EntityNotFoundError('출원데이터')

        hit = response.hits[0]
        source = hit.to_dict()

        result = self._transform_to_response_format(source)
        self._logging_es_query(search)

        return result

    async def search_application_source_by_app_num_or_reg_num_or_inter_num(
            self,
            search_number: str
    ) -> Optional[Dict[str, Any]]:

        """
        application_number로 먼저 조회하고,
        없으면 reg_number로 조회한다.

        둘 다 없으면 debug 로그만 출력하고 None 반환.
        """

        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", application_number=search_number)
        response = await search.execute()

        if response.hits:
            hit = response.hits[0]
            self._logging_es_query(search)
            return self._transform_to_response_format(hit.to_dict())

        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", reg_number=search_number)
        response = await search.execute()

        if response.hits:
            hit = response.hits[0]
            self._logging_es_query(search)
            return self._transform_to_response_format(hit.to_dict())

        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", international_register_number=search_number)
        response = await search.execute()

        if response.hits:
            hit = response.hits[0]
            self._logging_es_query(search)
            return self._transform_to_response_format(hit.to_dict())

        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", app_reference_number=search_number)
        response = await search.execute()

        if response.hits:
            hit = response.hits[0]
            self._logging_es_query(search)
            return self._transform_to_response_format(hit.to_dict())

        logger.debug(f"출원번호/등록번호/국제등록번호({search_number})로 조회된 데이터가 없습니다.")
        self._logging_es_query(search)

        return None

    async def search_application_source_by_application_number_or_reg_number(
            self,
            application_number_or_reg_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        application_number로 먼저 조회하고,
        없으면 reg_number로 조회한다.

        둘 다 없으면 debug 로그만 출력하고 None 반환.
        """

        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", application_number=application_number_or_reg_number)
        response = await search.execute()

        if response.hits:
            hit = response.hits[0]
            return self._transform_to_response_format(hit.to_dict())

        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", reg_number=application_number_or_reg_number)
        response = await search.execute()

        if response.hits:
            hit = response.hits[0]
            return self._transform_to_response_format(hit.to_dict())

        search = AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
        search = search.query("term", international_register_number=application_number_or_reg_number)
        response = await search.execute()

        if response.hits:
            hit = response.hits[0]
            return self._transform_to_response_format(hit.to_dict())

        logger.debug(f"출원번호/등록번호/국제등록번호({application_number_or_reg_number})로 조회된 데이터가 없습니다.")
        self._logging_es_query(search)

        return None

    async def check_international_trademark_data(
            self,
            app_reference_number: str,
            goods: str
    ) -> bool:
        """
        app_reference_number + products.designated_goods_eng
        문자 단위 완전일치 여부 확인
        + ES _id == app_reference_number 까지 일치해야 True
        """

        search = (
            AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
            .extra(size=1)
            .source(False)
            .query(
                "bool",
                must=[
                    Q("term", app_reference_number=app_reference_number),
                    Q(
                        "nested",
                        path="products",
                        query=Q(
                            "term",
                            **{"products.designated_goods_eng": goods}
                        )
                    )
                ]
            )
        )
        self._logging_es_query(search)

        response = await search.execute()

        if response.hits.total.value == 0:
            return False

        hit = response.hits[0]

        if hit.meta.id == app_reference_number:
            return True

        return False

    async def get_trademark_goods(
            self,
            app_reference_number: str,
            goods: str
    ) -> list[str]:
        """
        - app_reference_number: 완전일치
        - goods: 부분일치
        - products.designated_goods_eng 를 모두 리스트로 반환
        """

        # 🔥 wildcard용 검색어 정규화
        goods_lower = goods.lower()

        search = (
            AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
            .extra(size=1)  # app_reference_number 기준 문서 1개면 충분
            .source(["products.designated_goods_eng"])
            .query(
                "bool",
                must=[
                    # ✅ app_reference_number 완전일치
                    Q("term", app_reference_number=app_reference_number),

                    # ✅ products.designated_goods_eng 부분일치
                    Q(
                        "nested",
                        path="products",
                        query=Q(
                            "wildcard",
                            **{
                                "products.designated_goods_eng": {
                                    "value": f"*{goods_lower}*",
                                    "case_insensitive": True
                                }
                            }
                        )
                    )
                ]
            )
        )

        self._logging_es_query(search)

        response = await search.execute()

        if response.hits.total.value == 0:
            return []

        hit = response.hits[0]

        # 🔒 ES _id까지 확인 (안전장치)
        if hit.meta.id != app_reference_number:
            return []

        results: list[str] = []

        # 🔥 nested products 전부 순회하면서 Python 단에서 최종 필터
        for product in hit.products:
            product_eng = product.designated_goods_eng
            if not product_eng:
                continue

            if goods_lower in product_eng.lower():
                results.append(product_eng)

        return results

    async def get_trademark_goods_prefix(
            self,
            app_reference_number: str,
            goods: str
    ) -> list[str]:
        """
        - app_reference_number: 완전일치
        - goods: 앞쪽 일치 (prefix match)
        - products.designated_goods_eng 를 모두 리스트로 반환
        """

        goods_lower = goods.lower()

        search = (
            AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
            .extra(size=1)
            .source(["products.designated_goods_eng"])
            .query(
                "bool",
                must=[
                    Q("term", app_reference_number=app_reference_number),
                    Q(
                        "nested",
                        path="products",
                        query=Q(
                            "wildcard",
                            **{
                                "products.designated_goods_eng": {
                                    "value": f"{goods_lower}*",
                                    "case_insensitive": True
                                }
                            }
                        )
                    )
                ]
            )
        )

        self._logging_es_query(search)

        response = await search.execute()

        if response.hits.total.value == 0:
            return []

        hit = response.hits[0]

        if hit.meta.id != app_reference_number:
            return []

        results: list[str] = []

        for product in hit.products:
            product_eng = product.designated_goods_eng
            if not product_eng:
                continue

            if product_eng.lower().startswith(goods_lower):
                results.append(product_eng)

        return results

    async def get_trademark_goods_suffix(
            self,
            app_reference_number: str,
            goods: str
    ) -> list[str]:
        """
        - app_reference_number: 완전일치
        - goods: 뒤쪽 일치 (suffix match)
        - products.designated_goods_eng 를 모두 리스트로 반환
        """

        goods_lower = goods.lower()

        search = (
            AsyncSearch(using=self.ALIAS, index=self.INDEX_NAME)
            .extra(size=1)
            .source(["products.designated_goods_eng"])
            .query(
                "bool",
                must=[
                    Q("term", app_reference_number=app_reference_number),
                    Q(
                        "nested",
                        path="products",
                        query=Q(
                            "wildcard",
                            **{
                                "products.designated_goods_eng": {
                                    "value": f"*{goods_lower}",
                                    "case_insensitive": True
                                }
                            }
                        )
                    )
                ]
            )
        )

        self._logging_es_query(search)

        response = await search.execute()

        if response.hits.total.value == 0:
            return []

        hit = response.hits[0]

        if hit.meta.id != app_reference_number:
            return []

        results: list[str] = []

        for product in hit.products:
            product_eng = product.designated_goods_eng
            if not product_eng:
                continue

            if product_eng.lower().endswith(goods_lower):
                results.append(product_eng)

        return results

    def _build_mark_name_query(self, mark_name: str) -> List[Q]:
        lang_type = self._classify_text_language(mark_name)
        original = mark_name

        queries = []

        match lang_type:
            case 'korean':
                queries = [
                    # 한글 상표명 - whitespace 필드
                    Q("term", **{"trademark_name_kor_whitespace": original}),
                    Q("term", **{"trademark_name_kor_whitespace.exact": original}),
                    Q("term", **{"trademark_name_kor_whitespace.syn": original}),
                    Q("term", **{"trademark_name_kor_whitespace.nori": original}),
                    Q("term", **{"trademark_name_kor_whitespace.jamo": original}),
                    Q("term", **{"trademark_name_kor_whitespace.partial": original}),
                    Q("term", **{"trademark_name_kor_whitespace.front": original}),
                    Q("term", **{"trademark_name_kor_whitespace.back": original}),

                    # korsum 필드
                    Q("term", **{"korsum": original}),
                    Q("term", **{"korsum.nori": original}),
                    Q("term", **{"korsum.jamo": original}),
                    Q("term", **{"korsum.partial": original}),
                    Q("term", **{"korsum.front": original}),
                    Q("term", **{"korsum.back": original}),
                    Q("term", **{"korsum.syn": original}),

                    # match 쿼리 (분석기 활용)
                    Q("match", **{"trademark_name_kor_whitespace": original}),
                ]
            case 'english':
                queries = [
                    # 영어 상표명 - whitespace 필드
                    Q("term", **{"trademark_name_eng_whitespace": original}),
                    Q("term", **{"trademark_name_eng_whitespace.exact": original}),
                    Q("term", **{"trademark_name_eng_whitespace.syn": original}),
                    Q("term", **{"trademark_name_eng_whitespace.partial": original}),
                    Q("term", **{"trademark_name_eng_whitespace.front": original}),
                    Q("term", **{"trademark_name_eng_whitespace.back": original}),

                    # 대소문자 변형
                    Q("term", **{"trademark_name_eng_whitespace": original.upper()}),
                    Q("term", **{"trademark_name_eng_whitespace": original.lower()}),
                    Q("term", **{"trademark_name_eng_whitespace.exact": original.upper()}),
                    Q("term", **{"trademark_name_eng_whitespace.exact": original.lower()}),

                    # engsum 필드
                    Q("term", **{"engsum": original}),
                    Q("term", **{"engsum.partial": original}),
                    Q("term", **{"engsum.front": original}),
                    Q("term", **{"engsum.back": original}),
                    Q("term", **{"engsum.syn": original}),
                    Q("term", **{"engsum": original.upper()}),
                    Q("term", **{"engsum": original.lower()}),

                    # engsumPronun 필드 (발음)
                    Q("term", **{"engsumPronun": original}),
                    Q("term", **{"engsumPronun.partial": original}),
                    Q("term", **{"engsumPronun.front": original}),
                    Q("term", **{"engsumPronun.back": original}),

                    # match 쿼리 (분석기 활용)
                    Q("match", **{"trademark_name_eng_whitespace": original}),
                ]
            case 'mixed':
                queries = [
                    # 한글 필드
                    Q("term", **{"trademark_name_kor_whitespace": original}),
                    Q("term", **{"trademark_name_kor_whitespace.exact": original}),
                    Q("term", **{"trademark_name_kor_whitespace.syn": original}),
                    Q("term", **{"trademark_name_kor_whitespace.nori": original}),
                    Q("term", **{"trademark_name_kor_whitespace.jamo": original}),
                    Q("term", **{"trademark_name_kor_whitespace.partial": original}),
                    Q("term", **{"trademark_name_kor_whitespace.front": original}),
                    Q("term", **{"trademark_name_kor_whitespace.back": original}),
                    Q("term", **{"korsum": original}),
                    Q("term", **{"korsum.nori": original}),
                    Q("term", **{"korsum.jamo": original}),
                    Q("term", **{"korsum.partial": original}),
                    Q("term", **{"korsum.front": original}),
                    Q("term", **{"korsum.back": original}),
                    Q("term", **{"korsum.syn": original}),

                    # 영어 필드
                    Q("term", **{"trademark_name_eng_whitespace": original}),
                    Q("term", **{"trademark_name_eng_whitespace.exact": original}),
                    Q("term", **{"trademark_name_eng_whitespace.syn": original}),
                    Q("term", **{"trademark_name_eng_whitespace.partial": original}),
                    Q("term", **{"trademark_name_eng_whitespace.front": original}),
                    Q("term", **{"trademark_name_eng_whitespace.back": original}),
                    Q("term", **{"trademark_name_eng_whitespace": original.upper()}),
                    Q("term", **{"trademark_name_eng_whitespace": original.lower()}),
                    Q("term", **{"engsum": original}),
                    Q("term", **{"engsum.partial": original}),
                    Q("term", **{"engsum.front": original}),
                    Q("term", **{"engsum.back": original}),
                    Q("term", **{"engsum.syn": original}),
                    Q("term", **{"engsum": original.upper()}),
                    Q("term", **{"engsum": original.lower()}),
                    Q("term", **{"engsumPronun": original}),
                    Q("term", **{"engsumPronun.partial": original}),
                    Q("term", **{"engsumPronun.front": original}),
                    Q("term", **{"engsumPronun.back": original}),

                    # match 쿼리
                    Q("match", **{"trademark_name_kor_whitespace": original}),
                    Q("match", **{"trademark_name_eng_whitespace": original}),
                ]
        queries.extend(self._build_queries_for_clean_mark_name(mark_name))

        return queries

    def _build_queries_for_clean_mark_name(self, mark_name: str) -> List[Q]:
        lang_type = self._classify_text_language(mark_name)
        original = mark_name
        clean_name = mark_name.replace(" ", "").replace("-", "").replace("_", "")

        if clean_name == original:
            return []

        match lang_type:
            case 'korean':
                return [
                    Q("term", **{"trademark_name_kor_whitespace": clean_name}),
                    Q("term", **{"korsum": clean_name}),
                    Q("match", **{"trademark_name_kor_whitespace": clean_name}),
                ]

            case 'english':
                return [
                    Q("term", **{"trademark_name_eng_whitespace": clean_name}),
                    Q("term", **{"trademark_name_eng_whitespace": clean_name.upper()}),
                    Q("term", **{"trademark_name_eng_whitespace": clean_name.lower()}),
                    Q("term", **{"engsum": clean_name}),
                    Q("term", **{"engsum": clean_name.upper()}),
                    Q("term", **{"engsum": clean_name.lower()}),
                    Q("match", **{"trademark_name_eng_whitespace": clean_name}),
                ]

            case 'mixed':
                return [
                    Q("term", **{"trademark_name_kor_whitespace": clean_name}),
                    Q("term", **{"korsum": clean_name}),
                    Q("term", **{"trademark_name_eng_whitespace": clean_name}),
                    Q("term", **{"trademark_name_eng_whitespace": clean_name.upper()}),
                    Q("term", **{"trademark_name_eng_whitespace": clean_name.lower()}),
                    Q("term", **{"engsum": clean_name}),
                    Q("term", **{"engsum": clean_name.upper()}),
                    Q("term", **{"engsum": clean_name.lower()}),
                    Q("match", **{"trademark_name_kor_whitespace": clean_name}),
                    Q("match", **{"trademark_name_eng_whitespace": clean_name}),
                ]

    @classmethod
    def _format_hits(cls, response):
        """검색 결과 포맷팅"""
        results = []
        for hit in response:
            get = lambda obj, attr, default=None: getattr(obj, attr, default)

            applicant = hit.applicants or [{}]
            agent = hit.agents or [{}]
            product = hit.products or [{}]

            application_number = get(hit, 'application_number')

            results.append({
                'application_number': format_number(application_number),
                'mark_image_url': get(hit, 'image_path'),
                'mark_name': get(hit, 'trademark_name_kor') or get(hit, 'trademark_name_eng'),
                "goods_name": get(product, 'designated_goods_kor') or get(product, 'designated_goods_eng'),
                "agent": cls._format_agents(agent, get),
                "applicant": cls._format_applicants(applicant, get),
                "goods_class": cls._format_goods(product, get),
            })
        return results

    @classmethod
    def _format_agents(cls, agents: List[Dict[str, str]], _get: Callable):
        """대리인 정보 포맷팅"""
        return [{
            "agent_name": _get(agent, 'customer_kor_name'),
            "agent_number": format_number(_get(agent, 'customer_code'))
        } for agent in (agents or [{}]) if agent]

    @classmethod
    def _format_applicants(cls, applicants: List[Dict[str, str]], _get: Callable):
        """출원인 정보 포맷팅"""
        return [{
            "applicant_name": _get(applicant, 'customer_kor_name'),
            "patent_customer_number": format_number(_get(applicant, 'customer_code'))
        } for applicant in (applicants or [{}]) if applicant]

    @classmethod
    def _format_goods(cls, products: List[Dict[str, str]], _get: Callable):
        """지정상품 정보 포맷팅"""
        result: dict[str, list[str]] = {}

        for p in products:
            main_code = _get(p, 'main_code')
            if not main_code:
                continue
            try:
                main_code = int(main_code)
            except ValueError:
                main_code = str(main_code)

            goods_name = _get(p, 'designated_goods_kor')

            if main_code not in result:
                result[main_code] = []
            if goods_name and goods_name not in result[main_code]:
                result[main_code].append(goods_name)

        return result

    def _transform_to_response_format(self, source: Dict[str, Any]) -> Dict[str, Any]:
        # 등록번호들 추출
        registration_numbers = []
        if source.get("registration_rights"):
            registration_numbers = [
                format_number(reg.get("registration_number"))
                for reg in source["registration_rights"]
                if reg.get("registration_number")
            ]

        # 고객 정보 변환
        customers = []
        if source.get("customers"):
            for customer in source["customers"]:
                customers.append({
                    "customer_type": customer.get("customer_type", ""),
                    "customer_name": customer.get("customer_kor_name", ""),
                    "customer_code": format_number(customer.get("customer_code", "")),
                    "customer_nationality": customer.get("customer_national_code", "")
                })

        # 출원인 정보 변환
        applicants = []
        if source.get("applicants"):
            for applicant in source["applicants"]:
                applicants.append({
                    "applicant_name": applicant.get("customer_kor_name", ""),
                    "applicant_name_eng": "",  # 매핑에 없음
                    "applicant_number": format_number(applicant.get("customer_code", "")),
                    "business_registration_number": ""  # 매핑에 없음
                })

        # 최종 권리자 정보 변환
        final_right_holders = []
        if source.get("registration_rights"):
            for reg_right in source["registration_rights"]:
                if reg_right.get("right_holders"):
                    for holder in reg_right["right_holders"]:
                        final_right_holders.append({
                            "right_holder_name": holder.get("rank_correlator_name", ""),
                            "right_holder_number": format_number(holder.get("rank_correlator_serial_number", "")),
                            "right_holder_country": ""  # 매핑에 없음
                        })

        # 대리인 정보 추출
        agents = []
        if source.get("agents"):
            agents = [{
                "agent_name": agent.get("customer_kor_name", ""),
                "agent_number": format_number(agent.get("customer_code", "")),
                "agent_code": format_number(agent.get("customer_code", ""))
            } for agent in source["agents"]]

        # 상품류 추출
        goods_classes = list(set(source.get("search_main_codes", [])))

        # 유사군 코드 추출
        similar_group_codes = list(set(source.get("search_sub_codes", [])))

        # 상품 분류 정보 변환
        goods_classifications = []
        goods_ko_and_en = {}
        if source.get("products"):
            # main_code와 sub_code별로 그룹핑
            grouped = {}
            for product in source["products"]:
                main_code = product.get("main_code", "")
                sub_code = product.get("sub_code", "")
                key = (main_code, sub_code)

                if key not in grouped:
                    grouped[key] = {
                        "main_code": main_code,
                        "sub_code": sub_code,
                        "product_names": [],
                        "product_eng_names": [],
                        "product_primary_name": "",
                        "product_eng_primary_name": ""
                    }

                if product.get("designated_goods_kor"):
                    grouped[key]["product_names"].append(product["designated_goods_kor"])
                if product.get("designated_goods_eng"):
                    grouped[key]["product_eng_names"].append(product["designated_goods_eng"])

                if main_code not in goods_ko_and_en:
                    goods_ko_and_en[main_code] = {}

                if sub_code not in goods_ko_and_en[main_code]:
                    goods_ko_and_en[main_code][sub_code] = {}

                ko = product.get("designated_goods_kor")
                en = product.get("designated_goods_eng")

                # 국문 + 영문이 모두 있을 때만 1:1 매핑
                if ko and en:
                    goods_ko_and_en[main_code][sub_code][ko] = en
                elif ko:
                    goods_ko_and_en[main_code][sub_code][ko] = ""

            goods_classifications = list(grouped.values())

        # 일부 거절 상품 분류 정보
        partial_reject_goods_classifications = []
        if source.get("partial_reject_products"):
            grouped = {}
            for product in source["partial_reject_products"]:
                main_code = product.get("main_code", "")
                sub_code = product.get("sub_code", "")
                key = (main_code, sub_code)

                if key not in grouped:
                    grouped[key] = {
                        "main_code": main_code,
                        "sub_code": sub_code,
                        "product_names": [],
                        "product_eng_names": [],
                        "product_primary_name": "",
                        "product_eng_primary_name": ""
                    }

                if product.get("designated_goods_kor"):
                    grouped[key]["product_names"].append(product["designated_goods_kor"])
                if product.get("designated_goods_eng"):
                    grouped[key]["product_eng_names"].append(product["designated_goods_eng"])

            partial_reject_goods_classifications = list(grouped.values())

        # 비엔나 코드 정보
        vienna_codes = []
        if source.get("vienna_codes"):
            for vienna in source["vienna_codes"]:
                vienna_codes.append({
                    "vienna_code": vienna.get("vienna_code", ""),
                    "vienna_code_description": vienna.get("vienna_code_description", "")
                })

        # 패밀리 출원 정보
        related_applications = []
        if source.get("family_applications"):
            for family in source["family_applications"]:
                related_applications.append({
                    "application_number": format_number(family.get("related_application_number", "")),
                    "application_date": family.get("related_application_date", "")
                })

        # 우선권 주장 정보
        priority_dates = []
        priority_numbers = []
        priority_claims = []
        if source.get("priority_claims"):
            for priority in source["priority_claims"]:
                if priority.get("priority_application_date"):
                    priority_dates.append(priority["priority_application_date"])
                if priority.get("priority_application_data"):
                    priority_numbers.append(format_number(priority["priority_application_data"]))

                priority_claims.append({
                    "priority_date": priority.get("priority_application_date", ""),
                    "priority_number": format_number(priority.get("priority_application_data", "")),
                    "priority_country": priority.get("priority_application_country", "")
                })

        # 등록 정보
        registrations = []
        if source.get("registration_rights"):
            for reg in source["registration_rights"]:
                registrations.append({
                    "registration_number": format_number(reg.get("registration_number", "")),
                    "registration_correlator_name": reg.get("last_right_holder_name", ""),
                    "registration_correlator_address": reg.get("last_right_holder_address", ""),
                    "registration_expiration_date": reg.get("expiration_date", ""),
                    "registration_date": reg.get("registration_date", "")
                })

        # 거절결정 정보
        reject_decision_info = {
            "has_reject_decision": bool(source.get("reject_decisions")),
            "send_number": "",
            "content_title": "",
            "attach_file_title": "",
            "guid_title": "",
            "pdf_file_name": "",
            "pdf_file_path": ""
        }
        if source.get("reject_decisions") and len(source["reject_decisions"]) > 0:
            first_reject = source["reject_decisions"][0]
            reject_decision_info.update({
                "send_number": format_number(first_reject.get("send_number", "")),
                "content_title": first_reject.get("reject_content_title", ""),
                "attach_file_title": first_reject.get("attach_file_title", ""),
                "guid_title": first_reject.get("guid_title", ""),
                "pdf_file_name": first_reject.get("pdf_file_name", ""),
                "pdf_file_path": first_reject.get("pdf_file_path", "")
            })

        # 의견제출통지 정보
        oa_info = {
            "has_oa": bool(source.get("opinion_reject_decisions")),
            "send_number": "",
            "content_title": "",
            "attach_file_title": "",
            "guid_title": "",
            "pdf_file_name": "",
            "pdf_file_path": ""
        }
        if source.get("opinion_reject_decisions") and len(source["opinion_reject_decisions"]) > 0:
            first_oa = source["opinion_reject_decisions"][0]
            oa_info.update({
                "send_number": format_number(first_oa.get("send_number", "")),
                "content_title": first_oa.get("reject_content_title", ""),
                "attach_file_title": first_oa.get("attach_file_title", ""),
                "guid_title": first_oa.get("guid_title", ""),
                "pdf_file_name": first_oa.get("pdf_file_name", ""),
                "pdf_file_path": first_oa.get("pdf_file_path", "")
            })

        # 최종 응답 구성
        result = {
            "application_number": format_number(
                source.get("application_number", source.get('app_reference_number', ''))),
            "registration_numbers": registration_numbers,
            "trademark_type": source.get("trademark_division_dcode", ""),
            "registration_status": source.get("reg_status", ""),
            "final_disposition": source.get("last_disposal_code", ""),
            "trademark_name_kor": source.get("trademark_name_kor", ""),
            "trademark_name_eng": source.get("trademark_name_eng", ""),
            "application_date": self._format_date(source.get("application_date")),
            "publication_date": self._format_date(source.get("publication_date")),
            "registration_public_date": self._format_date(source.get("reg_public_date")),
            "registration_dates": [self._format_date(source.get("reg_date"))] if source.get("reg_date") else [],
            "final_disposition_date": self._format_date(source.get("last_disposal_date")),
            "priority_dates": [self._format_date(d) for d in priority_dates],
            "international_registration_date": self._format_date(source.get("international_register_date")),
            "designate_date": self._format_date(source.get("designate_date")),
            "expiration_date": "",  # registration_rights에서 가져와야 함
            "publication_number": format_number(source.get("publication_number", "")),
            "registration_public_number": format_number(source.get("reg_public_number", "")),
            "priority_numbers": priority_numbers,
            "international_registration_number": format_number(source.get("international_register_number", "")),
            "priority_claims": priority_claims,
            "customers": customers,
            "applicants": applicants,
            "final_right_holders": final_right_holders,
            "agents": agents,
            "goods_classes": goods_classes,
            "similar_group_codes": similar_group_codes,
            "goods_classifications": goods_classifications,
            "partial_reject_goods_classifications": partial_reject_goods_classifications,
            "vienna_codes": vienna_codes,
            "related_applications": related_applications,
            "is_image": source.get("image_flag", False),
            "path_info": {
                "image_path": source.get("image_path", ""),
                "small_image_path": source.get("small_image_path", ""),
                "publication_path": source.get("publication_path", ""),
                "registration_gazette_path": source.get("reg_gazette_path", ""),
                "publication_pdf_name": source.get("publication_pdf_name", ""),
                "registration_gazette_pdf_name": source.get("reg_gazette_pdf_name", ""),
                "image_flag": "Y" if source.get("image_flag") else "N",
                "publication_flag": "Y" if source.get("publication_flag") else "N",
                "registration_gazette_flag": "Y" if source.get("reg_public_gazette_flag") else "N"
            },
            "reject_decision_info": reject_decision_info,
            "oa_info": oa_info,
            "registrations": registrations,
            "country": "KO",
            "product_ko_and_en": goods_ko_and_en
        }

        return result

    @staticmethod
    def _format_date(date_str: Optional[str]) -> str:
        """
        날짜 문자열을 YYYY-MM-DD 형식으로 변환합니다.

        Args:
            date_str: YYYYMMDD 형식의 날짜 문자열

        Returns:
            YYYY-MM-DD 형식의 날짜 문자열 또는 빈 문자열
        """
        if not date_str or len(date_str) != 8:
            return ""

        try:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except (ValueError, IndexError):
            return ""
