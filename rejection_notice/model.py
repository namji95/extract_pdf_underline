from dataclasses import dataclass
from typing import Generic, TypeVar

PageItem = TypeVar('PageItem')


@dataclass
class PaginationInfo:
    """페이지네이션 정보를 담는 데이터 클래스

    Attributes:
        offset: 데이터베이스 쿼리용 오프셋
        limit: 페이지당 항목 수
        page: 현재 페이지 번호 (1부터 시작)
        total_count: 전체 항목 수
        total_pages: 전체 페이지 수
    """
    offset: int
    limit: int
    page: int
    total_count: int = 0
    total_pages: int = 0


class PaginatedResult(Generic[PageItem]):
    """페이지네이션된 결과를 담는 제네릭 클래스

    Attributes:
        items: 실제 데이터 목록
        pagination: 페이지네이션 정보
        meta: 추가 메타 정보
    """

    def __init__(self, items: PageItem, pagination: PaginationInfo, **kwargs):
        self.items = items
        self.pagination = pagination
        self.meta: dict = kwargs

    @property
    def total_count(self) -> int:
        return self.pagination.total_count

    @property
    def total_pages(self) -> int:
        return self.pagination.total_pages

    @property
    def current_page(self) -> int:
        return self.pagination.page

    @property
    def limit(self) -> int:
        return self.pagination.limit

    def to_dict(self) -> dict:
        """딕셔너리 형태로 변환"""
        result = {
            "items": self.items,
            "pagination": {
                "total_count": self.pagination.total_count,
                "total_pages": self.pagination.total_pages,
                "current_page": self.pagination.page,
                "limit": self.pagination.limit
            }
        }
        if self.meta:
            result["meta"] = self.meta
        return result

    @property
    def pagination_info(self):
        return {
            "total_count": self.pagination.total_count,
            "total_pages": self.pagination.total_pages,
            "current_page": self.pagination.page,
            "limit": self.pagination.limit
        }


class PaginationService:
    """페이지네이션 관련 공통 유틸리티 서비스"""

    @staticmethod
    def calculate_offset(page: int, limit: int) -> int:
        """페이지 번호와 limit으로 offset 계산

        Args:
            page: 페이지 번호 (1부터 시작)
            limit: 페이지당 항목 수

        Returns:
            데이터베이스 쿼리용 offset
        """
        if page < 1:
            page = 1
        return (page - 1) * limit

    @staticmethod
    def calculate_total_pages(total_count: int, limit: int) -> int:
        """전체 개수와 limit으로 총 페이지 수 계산

        Args:
            total_count: 전체 항목 수
            limit: 페이지당 항목 수

        Returns:
            총 페이지 수
        """
        if total_count == 0 or limit == 0:
            return 0
        return (total_count + limit - 1) // limit

    @staticmethod
    def create_pagination_info(
            page: int,
            limit: int,
            offset: int,
            total_count: int
    ) -> PaginationInfo:
        """페이지네이션 정보 생성

        Args:
            page: 현재 페이지 번호
            limit: 페이지당 항목 수
            offset: 데이터베이스 쿼리용 오프셋
            total_count: 전체 항목 수

        Returns:
            PaginationInfo 객체
        """
        total_pages = PaginationService.calculate_total_pages(total_count, limit)

        return PaginationInfo(
            offset=offset,
            limit=limit,
            page=page,
            total_count=total_count,
            total_pages=total_pages
        )
