"""把界面用到的第三方前端库和字体复制进 src/claudedesk/assets/vendor/（结果已提交进仓库）。

只在升级这些库时需要跑：
    mkdir tmp && cd tmp && npm init -y && npm i markdown-it@14 katex@0.16 dompurify@3 \
        @highlightjs/cdn-assets@11 @fontsource-variable/inter @fontsource-variable/jetbrains-mono \
        @fontsource-variable/noto-sans-sc @fontsource-variable/source-serif-4 @fontsource-variable/noto-serif-sc
    python scripts/vendor.py tmp/node_modules
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "claudedesk" / "assets" / "vendor"

# (包, 选哪个 css, 只要哪些子集；None = 全部)
FONTS = [
    ("@fontsource-variable/inter", "wght.css", ("latin", "latin-ext")),
    ("@fontsource-variable/inter", "wght-italic.css", ("latin", "latin-ext")),
    ("@fontsource-variable/jetbrains-mono", "wght.css", ("latin", "latin-ext")),
    ("@fontsource-variable/jetbrains-mono", "wght-italic.css", ("latin",)),
    ("@fontsource-variable/source-serif-4", "wght.css", ("latin", "latin-ext")),
    ("@fontsource-variable/source-serif-4", "wght-italic.css", ("latin", "latin-ext")),
    ("@fontsource-variable/noto-sans-sc", "wght.css", None),
    ("@fontsource-variable/noto-serif-sc", "wght.css", None),
]


def fonts(nm: Path) -> None:
    dest = OUT / "fonts"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    css_out = []
    for pkg, css_name, subsets in FONTS:
        css = (nm / pkg / css_name).read_text(encoding="utf-8")
        for block in re.findall(r"/\*[^*]*\*/\s*@font-face\s*\{[^}]*\}", css):
            url = re.search(r"url\(\./files/([^)]+)\)", block).group(1)
            if subsets is not None and not any(re.search(rf"-{re.escape(s)}-(wght|standard)", url) for s in subsets):
                continue
            shutil.copy2(nm / pkg / "files" / url, dest / url)
            css_out.append(block.replace("./files/", "./fonts/"))
    (OUT / "fonts.css").write_text("\n\n".join(css_out) + "\n", encoding="utf-8")


def libs(nm: Path) -> None:
    copies = {
        "markdown-it/dist/markdown-it.min.js": "markdown-it.min.js",
        "dompurify/dist/purify.min.js": "purify.min.js",
        "katex/dist/katex.min.js": "katex/katex.min.js",
        "katex/dist/katex.min.css": "katex/katex.min.css",
        "katex/dist/contrib/copy-tex.min.js": "katex/copy-tex.min.js",
        "@highlightjs/cdn-assets/highlight.min.js": "highlight.min.js",
    }
    for src, dst in copies.items():
        (OUT / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(nm / src, OUT / dst)
    kf = OUT / "katex" / "fonts"
    shutil.rmtree(kf, ignore_errors=True)
    kf.mkdir()
    for f in (nm / "katex/dist/fonts").glob("*.woff2"):
        shutil.copy2(f, kf / f.name)
    # 只留 woff2：WebView2 都支持，省掉 woff / ttf
    css = (OUT / "katex/katex.min.css").read_text(encoding="utf-8")
    css = re.sub(r",url\(fonts/[^)]+\.woff\) format\(\"woff\"\),url\(fonts/[^)]+\.ttf\) format\(\"truetype\"\)", "", css)
    (OUT / "katex/katex.min.css").write_text(css, encoding="utf-8")
    licenses = OUT / "LICENSES.txt"
    parts = []
    for pkg in ("markdown-it", "dompurify", "katex", "@highlightjs/cdn-assets", *dict.fromkeys(p for p, *_ in FONTS)):
        lic = next((p for p in (nm / pkg).glob("LICENSE*")), None)
        if lic:
            parts.append(f"===== {pkg} =====\n{lic.read_text(encoding='utf-8', errors='replace').strip()}\n")
    licenses.write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    nm = Path(sys.argv[1]).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    libs(nm)
    fonts(nm)
    print("vendored into", OUT)
