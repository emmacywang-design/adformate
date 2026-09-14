#!/usr/bin/env python3
"""動畫圖示的結構與動態驗證。

結構檢查比對 git 靜態基準，確保動畫未破壞圖形幾何。
動態檢查在多個時間點截圖，確保動畫真的在跑 —— 只截第一幀無法證明這件事。

Usage:
    python3 verify-animations.py              # 檢查全部
    python3 verify-animations.py weather-rain # 只檢查指定圖示
Exit code: 0 = 全數通過，1 = 有失敗
"""
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ASSETS = ROOT / "assets"
BASELINE = "abc40ee"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# icon -> 預期的 @keyframes 名稱、預期的 class 出現次數
EXPECTED = {
    "weather-sunny":         {"keyframes": ["spin"],               "classes": {"spin": 1}},
    "weather-overcast":      {"keyframes": ["drift"],              "classes": {"cloud": 1}},
    "weather-cloudy":        {"keyframes": ["drift"],              "classes": {"cloud": 1}},
    "weather-rain":          {"keyframes": ["fall"],               "classes": {"drop": 3}},
    "weather-thunderstorm":  {"keyframes": ["fall", "flash"],      "classes": {"drop": 4, "bolt": 1}},
    "weather-sun-shower":    {"keyframes": ["fall", "shimmer"],    "classes": {"drop": 5, "ray": 5}},
    "weather-partly-cloudy": {"keyframes": ["shimmer", "drift"],   "classes": {"ray": 4, "cloud": 1}},
    "weather-snow":          {"keyframes": ["snowdrift"],          "classes": {"flake": 3}},
    "weather-fog":           {"keyframes": ["mist"],               "classes": {"fogline": 9}},
}

# 動態取樣點（毫秒）。刻意選非整數倍，避免恰好落在動畫週期的同一相位
SAMPLES = [120, 830, 1710, 2640]


def baseline_svg(name):
    r = subprocess.run(
        ["git", "show", f"{BASELINE}:instream-weather-icons/assets/{name}.svg"],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"讀不到基準檔 {name}: {r.stderr.strip()}")
    return r.stdout


def count_paths(svg):
    return len(re.findall(r"<path\b", svg))


def viewbox(svg):
    m = re.search(r'viewBox="([^"]+)"', svg)
    return m.group(1) if m else None


def count_class(svg, cls):
    return len(re.findall(r'class="[^"]*\b' + re.escape(cls) + r'\b[^"]*"', svg))


def check_structure(name, spec):
    """回傳失敗訊息列表，空列表代表通過。"""
    current = (ASSETS / f"{name}.svg").read_text()
    base = baseline_svg(name)
    fails = []

    if viewbox(current) != viewbox(base):
        fails.append(f"viewBox 被改動: {viewbox(base)} -> {viewbox(current)}")

    if count_paths(current) != count_paths(base):
        fails.append(f"path 數量被改動: {count_paths(base)} -> {count_paths(current)}")

    if "prefers-reduced-motion" not in current:
        fails.append("缺少 prefers-reduced-motion 區塊")

    for kf in spec["keyframes"]:
        if not re.search(r"@keyframes\s+" + re.escape(kf) + r"\b", current):
            fails.append(f"缺少 @keyframes {kf}")

    for cls, expected_n in spec["classes"].items():
        actual = count_class(current, cls)
        if actual != expected_n:
            fails.append(f"class '{cls}' 出現 {actual} 次，預期 {expected_n} 次")

    # 用到 transform 的動畫都必須設 fill-box，否則會繞畫布左上角公轉
    if "transform:" in current and "transform-box:fill-box" not in current.replace(" ", ""):
        fails.append("用了 transform 但缺少 transform-box:fill-box")

    return fails


def frame_hashes(name):
    """透過 <img> 載入 SVG，在多個時間點截圖並回傳雜湊。

    必須走 <img>，不可直接開 .svg —— 兩者的 CSS 執行環境不同。
    """
    hashes = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        page = td / "probe.html"
        page.write_text(
            '<!DOCTYPE html><meta charset="utf-8">'
            '<style>body{margin:0;background:#4a4a4a}'
            'img{display:block;width:160px;height:160px}</style>'
            f'<img src="{(ASSETS / (name + ".svg")).as_uri()}">')
        for ms in SAMPLES:
            shot = td / f"{ms}.png"
            subprocess.run(
                [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                 "--allow-file-access-from-files",
                 f"--virtual-time-budget={ms}",
                 f"--screenshot={shot}", "--window-size=160,160",
                 page.as_uri()],
                capture_output=True)
            if shot.exists():
                hashes.append(hashlib.sha256(shot.read_bytes()).hexdigest()[:12])
    return hashes


def main():
    targets = sys.argv[1:] or sorted(EXPECTED)
    bad = 0
    for name in targets:
        if name not in EXPECTED:
            raise SystemExit(f"未知的圖示: {name}")
        fails = check_structure(name, EXPECTED[name])

        hashes = frame_hashes(name)
        if len(hashes) < 2:
            fails.append(f"截圖失敗，只取得 {len(hashes)} 張")
        elif len(set(hashes)) < 2:
            fails.append(f"畫面在所有取樣點完全相同，動畫沒有在跑 (hash={hashes[0]})")

        if fails:
            bad += 1
            print(f"FAIL {name}")
            for f in fails:
                print(f"       {f}")
        else:
            print(f"PASS {name}  frames={len(set(hashes))}/{len(hashes)} unique")

    print(f"\n{len(targets) - bad}/{len(targets)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
