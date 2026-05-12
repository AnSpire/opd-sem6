import httpx

from app.config import settings


def get_http_client() -> httpx.AsyncClient:
    proxies = {"all://": settings.proxy_url} if settings.proxy_url else None
    return httpx.AsyncClient(proxies=proxies, timeout=30.0)
