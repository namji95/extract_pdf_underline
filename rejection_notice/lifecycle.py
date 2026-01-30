from __future__ import annotations

from contextlib import asynccontextmanager
from functools import wraps
from typing import AsyncIterator, Coroutine
from typing import Callable, TypeVar, Any


@asynccontextmanager
async def container_lifespan(container) -> AsyncIterator[None]:
    await container.init_resources()
    try:
        yield
    finally:
        await container.shutdown_resources()


T = TypeVar("T")


def with_resources(container) -> Callable[[Callable[..., Coroutine[Any, Any, T]]],
Callable[..., Coroutine[Any, Any, T]]]:
    def decorator(fn: Callable[..., Coroutine[Any, Any, T]]):
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            await container.init_resources()
            try:
                return await fn(*args, **kwargs)
            finally:
                await container.shutdown_resources()

        return wrapper

    return decorator
