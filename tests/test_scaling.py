from image_classifier.ui.scaling import MAX_SCALE, scale_css, ui_scale


class FakeScreen:
    def __init__(self, height, ratio):
        self._h, self._r = height, ratio

    def geometry(self):
        return self

    def height(self):
        return self._h

    def devicePixelRatio(self):
        return self._r


class FakeWidget:
    def __init__(self, height, ratio=1.0):
        self._screen = FakeScreen(height, ratio)

    def screen(self):
        return self._screen


def test_common_screens_keep_the_written_sizes():
    assert ui_scale(FakeWidget(1080)) == 1.0
    assert ui_scale(FakeWidget(1440)) == 1.0


def test_4k_screens_get_bigger_text_even_with_display_scaling():
    assert 1.4 < ui_scale(FakeWidget(1193, 1.75)) < 1.5  # 3840x2088 at 175%
    assert ui_scale(FakeWidget(4000, 2.0)) == MAX_SCALE


def test_no_widget_means_no_scaling():
    assert ui_scale(None) == 1.0


def test_scale_css_keeps_hairlines():
    assert scale_css("font-size: 10px; border: 1px solid red;", 2.0) == "font-size: 20px; border: 1px solid red;"
