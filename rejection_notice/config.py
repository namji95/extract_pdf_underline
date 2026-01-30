from dataclasses import dataclass

logging_prefix = '[Elasticsearch] '


@dataclass
class Config:
    es_host: str = '211.47.7.5'
    es_port: int = 9203
    es_alias: str = 'trademark_unified_current'


config = Config()
