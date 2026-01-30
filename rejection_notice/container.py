from typing import AsyncGenerator, Optional

from dependency_injector import containers, providers
from elasticsearch.dsl import async_connections
from loguru import logger

from rejection_notice.config import config
from rejection_notice.es import TrademarkEsRepository
from rejection_notice.lifecycle import with_resources

logging_prefix = '[Elasticsearch] '


async def init_es_connection(
        alias: str,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None
) -> AsyncGenerator[None, None]:
    try:
        # 인증 설정
        http_auth = None
        if username and password:
            http_auth = (username, password)

        # 연결 생성
        async_connections.create_connection(
            alias=alias,
            hosts=[{
                'host': host,
                'port': port,
                'scheme': 'http'
            }],
            http_auth=http_auth,
            timeout=30,
        )

        # 연결 테스트
        client = async_connections.get_connection(alias)
        info = await client.info()

        logger.info(
            f"{logging_prefix}ES {alias} 연결 성공: {host}:{port} - "
            f"클러스터: {info.get('cluster_name')}, "
            f"버전: {info.get('version', {}).get('number')}"
        )

        yield

    except Exception as e:
        logger.error(f"{logging_prefix}ES {alias} 연결 실패: {type(e).__name__}: {str(e)}")
        raise

    finally:
        try:
            client = async_connections.get_connection(alias)
            await client.close()
            logger.info(f"{logging_prefix}ES {alias} 연결 종료 완료")
        except Exception as e:
            logger.error(f"{logging_prefix}ES {alias} 연결 종료 실패: {type(e).__name__}: {str(e)}")


class CoreContainer(containers.DeclarativeContainer):
    """
    Elasticsearch
    """
    # connection
    es_connection_response = providers.Resource(
        init_es_connection,
        alias='trademark',
        host=config.es_host,
        port=config.es_port,
        username=None,
        password=None,
    )
    # repository
    es_repository = providers.Singleton(
        TrademarkEsRepository,
        index_name=config.es_alias
    )


container = CoreContainer()


@with_resources(container)
async def es_repository() -> 'TrademarkEsRepository':
    return container.es_repository()
