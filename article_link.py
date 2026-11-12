"""Safely retrieve *public* article HTML for user-triggered Grok analysis.

No paywall bypass, login, browser automation, or JavaScript execution.
This deliberately does not treat webpage instructions as assistant commands.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit, urlunsplit
import re
import socket

import requests
from bs4 import BeautifulSoup

MAX_HTML_BYTES = 1_500_000
MAX_ARTICLE_CHARS = 9_000
MAX_REDIRECTS = 3
MAX_LINK_CHARS = 2048


class ArticleFetchError(ValueError):
    """User-facing validation or article retrieval failure."""


@dataclass(frozen=True)
class FetchedArticle:
    url: str
    title: str
    text: str
    description: str
    publisher: str
    published_at: str
    basis: str  # '본문' or '제목·요약'
    fetched_at: str
    truncated: bool = False


def _validate_public_link(link: str) -> str:
    """Reject local/private services and unsupported schemes *before* requests."""
    link = str(link or '').strip()
    if not link or len(link) > MAX_LINK_CHARS:
        raise ArticleFetchError('기사 URL을 입력해 주세요(최대 2,048자).')
    try:
        parts = urlsplit(link)
        host = (parts.hostname or '').strip('.').lower()
        port = parts.port
    except ValueError as exc:
        raise ArticleFetchError('URL 형식 또는 포트가 올바르지 않습니다.') from exc
    if parts.scheme not in ('https', 'http') or not host or parts.username or parts.password:
        raise ArticleFetchError('http:// 또는 https://로 시작하는 공개 기사 링크만 입력할 수 있습니다.')
    if port not in (None, 80, 443):
        raise ArticleFetchError('일반 웹 포트(80·443)가 아닌 URL은 지원하지 않습니다.')
    if host in {'localhost', '0.0.0.0'} or host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid')):
        raise ArticleFetchError('내부망 또는 로컬 주소는 사용할 수 없습니다.')
    try:
        addresses = socket.getaddrinfo(host, port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise ArticleFetchError('기사 사이트 주소를 확인할 수 없습니다. URL을 확인해 주세요.') from exc
    if not addresses or any(not ip_address(addr[4][0]).is_global for addr in addresses):
        raise ArticleFetchError('공개 인터넷 주소로 확인되지 않는 링크는 사용할 수 없습니다.')
    return urlunsplit((parts.scheme, parts.netloc, parts.path or '/', parts.query, ''))


def _fetch_html(url: str, *, session: requests.Session | None = None) -> tuple[str, bytes]:
    owns_session = session is None
    session = session or requests.Session()
    if owns_session:
        # Do not use machine/environment HTTP proxies to reach arbitrary targets.
        session.trust_env = False
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; MarketPulsePublicArticle/1.0)',
        'Accept': 'text/html,application/xhtml+xml;q=0.9',
    }
    current = url
    try:
        for attempt in range(MAX_REDIRECTS + 1):
            current = _validate_public_link(current)
            try:
                response = session.get(current, headers=headers, timeout=(5, 12),
                                       allow_redirects=False, stream=True)
            except requests.RequestException as exc:
                raise ArticleFetchError('기사 사이트 연결에 실패했습니다. 주소와 인터넷 연결을 확인해 주세요.') from exc
            with response:
                if 300 <= response.status_code < 400:
                    location = response.headers.get('Location')
                    if not location:
                        raise ArticleFetchError('기사 사이트의 이동 주소를 확인할 수 없습니다.')
                    if attempt == MAX_REDIRECTS:
                        raise ArticleFetchError('기사 페이지 이동 횟수가 너무 많습니다.')
                    current = urljoin(current, location)
                    continue
                if response.status_code in (401, 403, 402):
                    raise ArticleFetchError('로그인·유료 구독·접근 제한이 있는 기사입니다. 공개 링크를 사용해 주세요.')
                if response.status_code >= 400:
                    raise ArticleFetchError(f'기사를 가져오지 못했습니다(HTTP {response.status_code}).')
                content_type = response.headers.get('Content-Type', '').lower()
                if content_type and not any(t in content_type for t in ('text/html', 'application/xhtml+xml')):
                    raise ArticleFetchError('HTML 기사 페이지만 지원합니다(PDF·이미지 파일 제외).')
                length = response.headers.get('Content-Length', '')
                if length.isdigit() and int(length) > MAX_HTML_BYTES:
                    raise ArticleFetchError('기사 페이지 용량이 제한을 초과합니다.')
                content = bytearray()
                try:
                    for chunk in response.iter_content(chunk_size=32 * 1024):
                        content.extend(chunk)
                        if len(content) > MAX_HTML_BYTES:
                            raise ArticleFetchError('기사 페이지 용량이 제한을 초과합니다.')
                except requests.RequestException as exc:
                    raise ArticleFetchError('기사 전송이 중단되었습니다.') from exc
                if not content:
                    raise ArticleFetchError('기사 페이지가 비어 있습니다.')
                return current, bytes(content)
        raise ArticleFetchError('기사 페이지 이동 횟수가 너무 많습니다.')
    finally:
        if owns_session:
            session.close()


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def _meta(soup: BeautifulSoup, *keys: str) -> str:
    for key in keys:
        node = soup.find('meta', attrs={'property': key}) or soup.find('meta', attrs={'name': key})
        if node and node.get('content'):
            return _clean(str(node['content']))
    return ''


def _body_text(soup: BeautifulSoup) -> str:
    # Remove boilerplate before extracting article content, but keep article headings.
    for node in soup.select('script,style,noscript,iframe,svg,header,footer,nav,aside,form,button'):
        node.decompose()
    for node in soup.select('.advertisement,.advert,.ad_banner,.ad-wrap,.share,.comment,.comments,.related-news,.related_articles,.copyright,.reporter_info'):
        node.decompose()
    selectors = [
        '#dic_area', '#newsct_article', '#articleBodyContents', '#article_view',
        '[itemprop="articleBody"]', '.article-body', '.article_body', '.articleBody',
        '.article_view', '.news_end', '.news-content', '.news_content',
        'main article', 'article',
    ]
    candidates: list[str] = []
    for selector in selectors:
        for node in soup.select(selector)[:5]:
            text = _clean(node.get_text(' ', strip=True))
            if len(text) >= 80:
                candidates.append(text)
        # Strong news-site selectors are more reliable than generic fallback.
        if candidates and selector not in ('main article', 'article'):
            return max(candidates, key=len)
    if candidates:
        return max(candidates, key=len)
    # Fallback for plain article pages with no conventional container.
    container = soup.find('main') or soup.body
    if container:
        paragraphs = [_clean(p.get_text(' ', strip=True)) for p in container.find_all('p')]
        text = _clean(' '.join(p for p in paragraphs if len(p) > 30))
        if len(text) >= 100:
            return text
    return ''


def parse_article_html(url: str, html: bytes | str) -> FetchedArticle:
    """Extract article body, or clearly label title+description fallback."""
    soup = BeautifulSoup(html, 'html.parser')
    headline = soup.find('h1')
    title_tag = soup.find('title')
    title = (_meta(soup, 'og:title', 'twitter:title') or
             (_clean(headline.get_text(' ', strip=True)) if headline else '') or
             (_clean(title_tag.get_text(' ', strip=True)) if title_tag else ''))[:350]
    description = _meta(soup, 'og:description', 'description', 'twitter:description')[:1500]
    publisher = (_meta(soup, 'og:site_name', 'application-name') or (urlsplit(url).hostname or ''))[:120]
    published = _meta(soup, 'article:published_time', 'datePublished', 'pubdate')[:100]
    body = _body_text(soup)
    if len(body) >= 100 and len(title) >= 3:
        basis = '본문'
        text = body
    elif len(title) >= 3 and len(description) >= 40:
        basis = '제목·요약'
        text = f'기사 제목: {title}\n검색/페이지 요약: {description}'
    else:
        raise ArticleFetchError(
            '기사 본문이나 충분한 요약을 확인할 수 없습니다. 로그인·유료 기사 또는 자바스크립트 전용 페이지일 수 있습니다.'
        )
    is_truncated = len(text) > MAX_ARTICLE_CHARS
    return FetchedArticle(
        url=url, title=title, description=description, text=text[:MAX_ARTICLE_CHARS],
        publisher=publisher, published_at=published, basis=basis,
        fetched_at=datetime.now(timezone.utc).isoformat(), truncated=is_truncated,
    )


def fetch_public_article(url: str, *, session: requests.Session | None = None) -> FetchedArticle:
    """User-click-only public HTML extraction. No authenticated/paywalled access."""
    final_url, content = _fetch_html(url, session=session)
    return parse_article_html(final_url, content)
