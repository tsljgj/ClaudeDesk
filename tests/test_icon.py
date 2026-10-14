import pytest
from claudedesk.icon import BADGE, DOT, badge_text, overlay_state, render, render_badge, save_ico
from PIL import Image

SIZES = [16, 20, 24, 32, 36]


def pixels(im):
    b = im.convert("RGBA").tobytes()
    return zip(b[0::4], b[1::4], b[2::4], b[3::4])


def reds(im, box=None):
    """角标红的像素数（容差留给缩小时的抗锯齿；橙色渐变的末端 g≥59，不算）。"""
    im = im.crop(box) if box else im
    return sum(1 for r, g, b, a in pixels(im) if a > 200 and abs(r - BADGE[0]) < 40 and g < 42 and b < 70)


def test_badge_text():
    assert [badge_text(n) for n in (-1, 0, 1, 9, 10, 99, 100, 12345)] == ["", "", "1", "9", "10", "99", "99+", "99+"]


def test_overlay_state():
    assert overlay_state(0, 0) == ("", "")
    assert overlay_state(0, 2) == (DOT, "有待你决定的消息")
    assert overlay_state(3, 2) == ("3", "3 条未读")
    assert overlay_state(42, 0) == ("42", "42 条未读")
    assert overlay_state(150, 1) == ("99+", "99+ 条未读")


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("text", ["1", "7", "42", "88", "99+", DOT])
def test_render_badge(size, text):
    im = render_badge(size, text)
    assert im.mode == "RGBA" and im.size == (size, size)
    assert reds(im) > size  # 有一块像样的红底
    x0, y0, x1, y1 = im.getbbox()
    assert x1 == size and abs(y0 + y1 - size) <= 1  # 靠右，竖直居中（Win10 角标在右下、Win11 在右上）
    assert im.getpixel((size * 3 // 4, size // 2))[3] > 240
    if text == DOT:  # 小圆点只在右边
        assert im.crop((0, 0, size // 3, size)).getchannel("A").getextrema()[1] < 40
    elif len(text) >= 2:  # 胶囊 / 圆角块比圆矮：最上、最下一行是空的
        assert im.crop((0, 0, size, 1)).getchannel("A").getextrema()[1] < 40
        assert im.crop((0, size - 1, size, size)).getchannel("A").getextrema()[1] < 40


@pytest.mark.parametrize("size", SIZES)
def test_badge_digits_differ(size):
    """字真的画上去了：不同的数画出来不一样，而且红底里有白字。"""
    imgs = [render_badge(size, t).tobytes() for t in ("1", "7", "42", "99+")]
    assert len(set(imgs)) == 4
    im = render_badge(size, "7")
    inner = im.crop((size // 4, size // 4, size * 3 // 4, size * 3 // 4))
    assert any(a > 200 and min(r, g, b) > 200 for r, g, b, a in pixels(inner))


def test_render_badge_empty_is_transparent():
    assert render_badge(20, "").getbbox() is None


@pytest.mark.parametrize("size", [16, 20, 24, 36, 64])
@pytest.mark.parametrize("count", [1, 12, 150])
def test_tray_count_badge(size, count):
    im = render(size, count=count)
    assert im.mode == "RGBA" and im.size == (size, size)
    h = size // 2
    assert reds(im, (h, h, size, size)) > size // 2  # 右下角是红底角标
    assert reds(im, (0, 0, size, size * 3 // 10)) == 0  # 上面露出 "C"
    assert render(size, count=count, alert=True).tobytes() != im.tobytes()


@pytest.mark.parametrize("size", [16, 24, 36])
def test_tray_no_badge(size):
    im = render(size)
    assert im.size == (size, size)
    assert reds(im) == 0  # 0 条未读：没有角标
    assert render(size, count=0).tobytes() == im.tobytes()
    p = render(size, pending=True)  # 有待决定但都看过：右上角一个红点，不是数字
    h = size // 2
    assert reds(p, (h, 0, size, h)) > 0 and reds(p, (0, h, size, size)) == 0


def test_exe_icon(tmp_path):
    out = tmp_path / "x.ico"
    save_ico(str(out))
    ico = Image.open(out)
    assert {(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)} <= set(ico.info["sizes"])
    ico.size = (32, 32)
    assert reds(ico.convert("RGBA")) == 0  # 程序图标不带数字 / 红点
