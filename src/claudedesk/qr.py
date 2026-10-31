"""二维码（手机访问的链接用手机扫）。只用标准库：字节模式、纠错等级 M、版本 1–10（最多 213 字节，够放一个链接）。

按 ISO/IEC 18004 的步骤：编码 → Reed-Solomon 纠错码 → 分块交错 → 画功能图形 → 之字形放数据 → 选罚分最少的掩码
→ 写格式信息 / 版本信息。tests/test_qr.py 拿 qrcode 包（有的话）逐格对照。
"""
from __future__ import annotations

# 版本 -> (每块纠错码字数, [(块数, 每块数据码字数), …])，纠错等级 M
_BLOCKS_M = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
    6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}
_FORMAT_M = 0b00  # 纠错等级 M 在格式信息里的两位


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _gf_mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _gf_mul(root, 0x02)
    return out


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    out = [0] * len(divisor)
    for b in data:
        factor = b ^ out.pop(0)
        out.append(0)
        for i, c in enumerate(divisor):
            out[i] ^= _gf_mul(c, factor)
    return out


def _capacity(version: int) -> int:
    return sum(n * k for n, k in _BLOCKS_M[version][1])


def _codewords(data: bytes, version: int) -> list[int]:
    """数据 → 加上纠错码、交错好的码字序列。"""
    bits: list[int] = []

    def put(v: int, n: int) -> None:
        bits.extend((v >> i) & 1 for i in range(n - 1, -1, -1))

    put(0b0100, 4)  # 字节模式
    put(len(data), 8 if version < 10 else 16)
    for b in data:
        put(b, 8)
    cap = _capacity(version) * 8
    put(0, min(4, cap - len(bits)))  # 结束符
    put(0, -len(bits) % 8)
    cws = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(cws) < _capacity(version):
        cws.append(pad)
        pad ^= 0xEC ^ 0x11
    ec_len, groups = _BLOCKS_M[version]
    div = _rs_divisor(ec_len)
    blocks, pos = [], 0
    for n, k in groups:
        for _ in range(n):
            blocks.append(cws[pos:pos + k])
            pos += k
    eccs = [_rs_remainder(b, div) for b in blocks]
    out = [b[i] for i in range(max(map(len, blocks))) for b in blocks if i < len(b)]
    return out + [e[i] for i in range(ec_len) for e in eccs]


_MASKS = [
    lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]


class _Grid:
    def __init__(self, version: int):
        self.v = version
        self.n = version * 4 + 17
        self.m = [[False] * self.n for _ in range(self.n)]  # m[y][x]
        self.fn = [[False] * self.n for _ in range(self.n)]  # 功能图形（不放数据、不加掩码）

    def set(self, x: int, y: int, dark: bool) -> None:
        self.m[y][x] = dark
        self.fn[y][x] = True

    def functions(self) -> None:
        n = self.n
        for i in range(n):  # 定时图形
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # 定位图形（连同分隔带）
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _ALIGN[self.v]
        last = len(pos) - 1
        for i, ax in enumerate(pos):  # 校正图形（和定位图形重叠的三个角不画）
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)  # 先占位，选好掩码再写真的
        if self.v >= 7:
            rem = self.v
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.v << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def format_bits(self, mask: int) -> None:
        n = self.n
        data = _FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit(i))
        self.set(8, n - 8, True)  # 固定的暗模块

    def place(self, cws: list[int]) -> None:
        n, i, total = self.n, 0, len(cws) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            up = (right + 1) & 2 == 0
            for vert in range(n):
                y = n - 1 - vert if up else vert
                for j in range(2):
                    x = right - j
                    if not self.fn[y][x] and i < total:
                        self.m[y][x] = (cws[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        f = _MASKS[mask]
        for y in range(self.n):
            for x in range(self.n):
                if not self.fn[y][x] and f(x, y):
                    self.m[y][x] = not self.m[y][x]

    def penalty(self) -> int:
        n, m, score = self.n, self.m, 0
        lines = [row for row in m] + [[m[y][x] for y in range(n)] for x in range(n)]
        for line in lines:
            run, prev = 0, None
            for c in line:
                if c == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, prev = 1, c
            if run >= 5:
                score += run - 2
            s = "".join("1" if c else "0" for c in line)
            for pat in ("10111010000", "00001011101"):  # 像定位图形的一段：1:1:3:1:1 一侧带 4 格空白
                k = s.find(pat)
                while k >= 0:
                    score += 40
                    k = s.find(pat, k + 1)
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in m)
        score += abs(dark * 20 - n * n * 10) // (n * n) * 10
        return score


def matrix(text: str, mask: int | None = None) -> list[list[bool]]:
    """text（UTF-8）的二维码模块：m[行][列]，True = 深色。mask 给定就用它（测试对照用），否则挑罚分最少的。"""
    data = text.encode("utf-8")
    version = next((v for v in _BLOCKS_M if len(data) + (2 if v < 10 else 3) <= _capacity(v)), None)
    if version is None:
        raise ValueError(f"太长了：二维码最多放 {_capacity(10) - 3} 字节")
    cws = _codewords(data, version)
    best = None
    for k in ([mask] if mask is not None else range(8)):
        g = _Grid(version)
        g.functions()
        g.place(cws)
        g.apply_mask(k)
        g.format_bits(k)
        p = g.penalty()
        if best is None or p < best[0]:
            best = (p, g)
    return best[1].m


def svg(text: str, border: int = 4) -> str:
    """二维码的 SVG：深色模块用 currentColor（界面上用 CSS 变量给它固定的深色、白底，深色主题下也扫得出来）。"""
    m = matrix(text)
    n = len(m) + border * 2
    d = "".join(f"M{x + border} {y + border}h1v1h-1z" for y, row in enumerate(m) for x, c in enumerate(row) if c)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges" '
            f'role="img" aria-label="二维码"><path fill="currentColor" d="{d}"/></svg>')
