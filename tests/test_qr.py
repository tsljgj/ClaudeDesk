"""二维码（qr.py）：拿 qrcode 包逐格对照（各种长度、版本 1–10、8 种掩码），再看 SVG 和太长时的报错。"""
import pytest
from claudedesk import qr


def test_matches_the_qrcode_package_module_by_module():
    qrcode = pytest.importorskip("qrcode")
    import qrcode.util

    base = "http://100.101.102.103:47821/?k=" + "AbCdEfGhIj-_" * 20
    bad = []
    for n in (1, 14, 26, 43, 62, 84, 106, 122, 152, 180, 210):
        text = base[:n]
        for mask in range(8):
            q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, mask_pattern=mask)
            q.add_data(qrcode.util.QRData(text.encode(), mode=qrcode.util.MODE_8BIT_BYTE))
            q.make(fit=True)
            if q.get_matrix() != qr.matrix(text, mask=mask):
                bad.append((n, mask, q.version))
    assert bad == []


def test_svg_and_limits():
    m = qr.matrix("http://pc.tailnet.ts.net:47821/?k=" + "x" * 32)
    assert len(m) in (33, 37, 41) and all(len(r) == len(m) for r in m)
    url = "http://192.168.1.20:47821/?k=abc"
    n = len(qr.matrix(url)) + 8  # 四周各留四格空白
    s = qr.svg(url)
    assert s.startswith("<svg") and 'fill="currentColor"' in s and f'viewBox="0 0 {n} {n}"' in s
    with pytest.raises(ValueError):
        qr.matrix("x" * 300)
