import os
import re

from enigma import getDesktop
from skin import loadSkin

def scale_skin(skin, minimum_size=(1200, 600)):
    try:
        desktop = getDesktop(0).size()
        match = re.search(r'<screen[^>]*\bsize="(\d+),(\d+)"', skin)
        if not match:
            return skin
        width, height = int(match.group(1)), int(match.group(2))
        scale = min(float(desktop.width()) / width, float(desktop.height()) / height)
        if abs(scale - 1.0) < 0.01 or (scale > 1.0 and (width < minimum_size[0] or height < minimum_size[1])):
            return skin
        def scale_pair(item):
            return '%s="%d,%d"' % (item.group(1), max(1, round(int(item.group(2)) * scale)), max(1, round(int(item.group(3)) * scale)))
        skin = re.sub(r'(position|size)="(\d+),(\d+)"', scale_pair, skin)
        skin = re.sub(r'font="([^";]+);(\d+)"', lambda item: 'font="%s;%d"' % (item.group(1), max(1, round(int(item.group(2)) * scale))), skin)
        return re.sub(r'itemHeight="(\d+)"', lambda item: 'itemHeight="%d"' % max(1, round(int(item.group(1)) * scale)), skin)
    except Exception:
        return skin


def load_responsive_skin(path, cache_prefix):
    try:
        with open(path, "r") as source:
            skin = source.read()
        desktop = getDesktop(0).size()
        rendered = scale_skin(skin)
        if rendered == skin:
            loadSkin(path)
            return
        cache_path = "/tmp/.%s-skin-%dx%d.xml" % (cache_prefix, desktop.width(), desktop.height())
        with open(cache_path, "w") as target:
            target.write(rendered)
        loadSkin(cache_path)
    except Exception:
        loadSkin(path)
