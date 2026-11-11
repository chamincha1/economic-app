"""Curated 30 domestic stock symbols. This is a lookup list, NOT price data.

Symbols and labels may change with corporate actions; FinanceDataReader/KRX is
queried at runtime to determine whether actual price data remains available.
"""
from __future__ import annotations

CATALOG: tuple[tuple[str, str, str], ...] = (
    ('삼성전자', '005930', '반도체·전자'),
    ('SK하이닉스', '000660', '반도체·전자'),
    ('현대자동차', '005380', '자동차·부품'),
    ('기아', '000270', '자동차·부품'),
    ('NAVER', '035420', '인터넷·게임'),
    ('카카오', '035720', '인터넷·게임'),
    ('LG에너지솔루션', '373220', '배터리·화학'),
    ('삼성바이오로직스', '207940', '바이오·의약'),
    ('셀트리온', '068270', '바이오·의약'),
    ('현대모비스', '012330', '자동차·부품'),
    ('POSCO홀딩스', '005490', '철강·소재'),
    ('LG화학', '051910', '배터리·화학'),
    ('삼성SDI', '006400', '배터리·화학'),
    ('KB금융', '105560', '금융'),
    ('신한지주', '055550', '금융'),
    ('하나금융지주', '086790', '금융'),
    ('우리금융지주', '316140', '금융'),
    ('삼성물산', '028260', '산업·건설'),
    ('삼성생명', '032830', '금융'),
    ('SK이노베이션', '096770', '배터리·화학'),
    ('두산에너빌리티', '034020', '산업·건설'),
    ('한국전력', '015760', '에너지·통신'),
    ('KT', '030200', '에너지·통신'),
    ('SK텔레콤', '017670', '에너지·통신'),
    ('LG전자', '066570', '반도체·전자'),
    ('HD현대중공업', '329180', '산업·건설'),
    ('한화에어로스페이스', '012450', '산업·건설'),
    ('삼성전기', '009150', '반도체·전자'),
    ('엔씨소프트', '036570', '인터넷·게임'),
    ('크래프톤', '259960', '인터넷·게임'),
)

STOCKS = {name: code for name, code, _ in CATALOG}
STOCK_SECTORS = {name: sector for name, _, sector in CATALOG}
DEFAULT_SELECTED = ['삼성전자', 'SK하이닉스', 'NAVER']


def filter_catalog(query: str = '', sector: str = '전체') -> list[tuple[str, str, str]]:
    needle = query.casefold().strip()
    return [row for row in CATALOG if (sector == '전체' or row[2] == sector)
            and (not needle or needle in row[0].casefold() or needle in row[1])]
