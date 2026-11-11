from zipfile import ZipFile
from io import BytesIO
import pandas as pd
from disclosure_collector import fetch_corp_mapping, fetch_disclosures


def make_zip_bytes():
    xml = b'<result><list><corp_code>00000001</corp_code><corp_name>A</corp_name><stock_code>005930</stock_code></list></result>'
    b = BytesIO()
    with ZipFile(b, 'w') as f: f.writestr('CORPCODE.xml', xml)
    return b.getvalue()


def test_corp_code_is_not_stock_code():
    class R:
        content = make_zip_bytes()
        def raise_for_status(self): pass
    mapping = fetch_corp_mapping(key='test', requester=lambda *_a, **_kw: R())
    assert mapping.iloc[0]['corp_code'] == '00000001'
    assert mapping.iloc[0]['stock_code'] == '005930'


def test_dart_filing_without_exact_clock_is_not_same_day_close_available():
    class R:
        def raise_for_status(self): pass
        def json(self):
            return {'status':'000','list':[{'rcept_dt':'20260102',
                    'rcept_no':'20260102000001','report_nm':'모의 공시'}]}
    mapping = pd.DataFrame([{'stock_code':'005930','corp_code':'00000001'}])
    out = fetch_disclosures('005930', '2026-01-01', '2026-01-10',
              key='test', mapping=mapping, requester=lambda *_a, **_kw: R())
    assert out.iloc[0]['published_at'].hour == 14  # 23:59 KST converted to 14:59 UTC
    assert out.iloc[0]['published_at'].minute == 59
