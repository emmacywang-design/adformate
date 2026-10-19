#!/usr/bin/env python3
"""把 Figma 匯出的 SVG 修正後內嵌進 index.html。

Figma 的遮罩不會隔離 multiply/screen 混合模式，但瀏覽器的 SVG mask 會，
直接使用會讓插畫顏色錯誤。這裡把遮罩下推到每個混合圖層上，並把每個檔案的
id 加上前綴，避免內嵌後互相衝突。

用法：python3 build.py   （讀 index.src.html + assets/src/*.svg，輸出 index.html）
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / 'assets' / 'src'
SVG_NS = 'http://www.w3.org/2000/svg'
NS = '{%s}' % SVG_NS
ET.register_namespace('', SVG_NS)

SKIP = {NS + 'defs', NS + 'mask', NS + 'clipPath'}


def blend_of(el):
    m = re.search(r'mix-blend-mode:\s*([a-z-]+)', el.get('style') or '')
    return m.group(1) if m else None


def set_blend(el, mode):
    style = re.sub(r'mix-blend-mode:\s*[a-z-]+;?', '', el.get('style') or '').strip()
    if mode:
        style = (style + ';' if style else '') + 'mix-blend-mode:' + mode
    if style:
        el.set('style', style)
    elif 'style' in el.attrib:
        del el.attrib['style']


def has_blend_desc(el):
    return any(blend_of(d) for d in el.iter() if d is not el)


def push_mask(group, mask, parents):
    """把 group 的遮罩分配到子層，讓混合模式能穿透到下方內容。"""
    for i, child in enumerate(list(group)):
        if child.tag in SKIP:
            continue
        plain_group = (child.tag == NS + 'g' and not blend_of(child)
                       and not child.get('mask') and not child.get('clip-path')
                       and not child.get('filter') and not child.get('transform'))
        if plain_group:
            push_mask(child, mask, parents)
        elif not child.get('mask'):
            child.set('mask', mask)
        else:
            wrapper = ET.Element(NS + 'g', {'mask': mask})
            set_blend(wrapper, blend_of(child))
            set_blend(child, None)
            group.remove(child)
            group.insert(i, wrapper)
            wrapper.append(child)
            parents[child] = wrapper
            parents[wrapper] = group


def fix_svg(text, prefix):
    root = ET.fromstring(text)
    parents = {c: p for p in root.iter() for c in p}

    def depth(el):
        d = 0
        while el in parents:
            el, d = parents[el], d + 1
        return d

    # 外框裁切與 viewport 相同，拿掉以免隔離混合模式
    for el in root.iter():
        if el.get('clip-path') and has_blend_desc(el):
            del el.attrib['clip-path']

    # 由內而外處理，巢狀遮罩才會正確
    masked = [el for el in root.iter() if el.get('mask') and el.tag == NS + 'g' and has_blend_desc(el)]
    for el in sorted(masked, key=depth, reverse=True):
        mask = el.attrib.pop('mask')
        push_mask(el, mask, parents)

    # 跳出動畫套在 SVG 內的 <g>：transform 放在 svg 外層會隔離混合，陰影會先閃白
    pop = ET.Element(NS + 'g', {'class': 'pop'})
    for child in list(root):
        root.remove(child)
        pop.append(child)
    root.append(pop)

    for attr in ('width', 'height'):
        root.attrib.pop(attr, None)
    root.set('aria-hidden', 'true')
    out = ET.tostring(root, encoding='unicode')
    out = re.sub(r'\sxmlns:ns\d+="[^"]+"', '', out)
    out = re.sub(r'id="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', out)
    out = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{prefix}-{m.group(1)})', out)
    out = re.sub(r'href="#([^"]+)"', lambda m: f'href="#{prefix}-{m.group(1)}"', out)
    return out


def main():
    html = (ROOT / 'index.src.html').read_text(encoding='utf-8')

    def inline(m):
        name, prefix = m.group(1), m.group(2) or m.group(1)
        return fix_svg((SRC / f'{name}.svg').read_text(encoding='utf-8'), prefix)

    # <!-- inline:title --> 或 <!-- inline:title as title-2 -->（同一檔案多次內嵌時換 id 前綴）
    html = re.sub(r'<!--\s*inline:([\w-]+)(?:\s+as\s+([\w-]+))?\s*-->', inline, html)
    (ROOT / 'index.html').write_text(html, encoding='utf-8')
    print('index.html built,', round(len(html) / 1024), 'KB')


if __name__ == '__main__':
    main()
