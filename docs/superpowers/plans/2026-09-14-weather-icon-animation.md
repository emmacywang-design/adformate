# 天氣圖示 SVG 內嵌動畫 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `instream-weather-icons/assets/` 的 9 顆天氣圖示各自依物理語意動起來，動畫內嵌於 `.svg` 檔案內部，現有 `index.html` 不需修改。

**Architecture:** 動畫檔一律由 `build-animations.py` 從 git 靜態基準 `abc40ee` 重新生成，不編輯既有動畫檔。所有動畫定義集中在該腳本的 `ANIMATIONS` 字典。`verify-animations.py` 負責結構檢查（viewBox 與 path 數量比對基準、class 數量、keyframes 存在性）與動態檢查（多時間點截圖雜湊比對）。

**Tech Stack:** Python 3（標準庫，無外部相依）、CSS animations 內嵌於 SVG、Chrome headless 作為渲染與驗證工具。

---

## 設計依據

以下數值皆為瀏覽器 `getBBox()` 實測，非估算：

| Icon | path 組成 |
|---|---|
| `weather-sunny` | 9 條，整體 bbox 中心 `(40.10, 39.54)`，整顆旋轉 |
| `weather-overcast` | 1 條（雲） |
| `weather-cloudy` | 1 條（雲） |
| `weather-rain` | `[0]` 雲、`[1][2][3]` 雨滴 |
| `weather-thunderstorm` | `[0]` 雲、`[1]` 閃電、`[2][3][4][5]` 雨滴 |
| `weather-sun-shower` | `[0]-[4]` 雨滴、`[5]-[9]` 光芒、`[10]` 雲 |
| `weather-partly-cloudy` | `[0]-[3]` 光芒、`[4]` 雲 |
| `weather-snow` | 3 片雪花 × 3 筆劃：`[0-2]` `[3-5]` `[6-8]`，中心 `(40.00,25.79)` `(55.02,52.21)` `(24.98,52.21)` |
| `weather-fog` | 9 條獨立橫線 |

## File Structure

- **Create** `instream-weather-icons/build-animations.py` — 動畫定義與生成器。所有 CSS 集中於此，是唯一需要審閱的動畫來源
- **Create** `instream-weather-icons/verify-animations.py` — 結構與動態驗證
- **Modify** `instream-weather-icons/assets/weather-*.svg`（9 檔）— 由 build 腳本生成，不手動編輯
- **不修改** `instream-weather-icons/index.html` — `<img src>` 標記不需改動，這是選擇內嵌方案的主要理由

---

### Task 1: 驗證腳本

**Files:**
- Create: `instream-weather-icons/verify-animations.py`

- [ ] **Step 1: 寫驗證腳本**

```python
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
```

- [ ] **Step 2: 執行，確認它會失敗**

```bash
cd ~/adformate/instream-weather-icons && python3 verify-animations.py weather-sunny
```

Expected: `FAIL weather-sunny`，訊息包含「缺少 prefers-reduced-motion 區塊」、「缺少 @keyframes spin」、「class 'spin' 出現 0 次，預期 1 次」、「畫面在所有取樣點完全相同」。

這是應該的 —— 此時還沒有任何動畫。

- [ ] **Step 3: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/verify-animations.py
git commit -m "add verification harness for weather icon animations

Structural checks compare against the static baseline so an animation
edit can never silently damage icon geometry. Motion check samples
several virtual-time points because a single frame cannot prove an
animation is running.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: 生成器骨架 + `weather-sunny`

**Files:**
- Create: `instream-weather-icons/build-animations.py`
- Modify: `instream-weather-icons/assets/weather-sunny.svg`（由腳本生成）

- [ ] **Step 1: 寫生成器**

```python
#!/usr/bin/env python3
"""從靜態基準重新生成動畫版天氣圖示。

每個動畫 SVG 都是「基準檔 + 樣式 + class」的產物，絕不編輯既有動畫檔。
因此本腳本可重複執行且結果一致，也從結構上排除了動畫編輯破壞圖形幾何的可能。

Usage:
    python3 build-animations.py                    # 重建全部
    python3 build-animations.py weather-rain       # 只重建指定圖示
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
ASSETS = ROOT / "assets"
BASELINE = "abc40ee"

REDUCED = "@media(prefers-reduced-motion:reduce){*{animation:none!important}}"

# 繞自身中心變形的必要宣告。SVG 元素的 transform-origin 預設是畫布左上角 (0,0)，
# 少了這兩行，rotate() 會變成繞畫布角落公轉而不是自轉。
ORIGIN = "transform-box:fill-box;transform-origin:center;"

FALL = ("@keyframes fall{0%{transform:translateY(-4px);opacity:0}"
        "18%{opacity:1}72%{opacity:1}"
        "100%{transform:translateY(16px);opacity:0}}")

DRIFT = "@keyframes drift{0%,100%{transform:translateX(-3px)}50%{transform:translateX(3px)}}"

SHIMMER = ("@keyframes shimmer{0%,100%{opacity:.45;transform:scale(.88)}"
           "50%{opacity:1;transform:scale(1.12)}}")

# 每個圖示的動畫定義。
#   style        內嵌 CSS
#   root_class   加在既有外層 <g id="..."> 上的 class
#   path_classes {path 索引: class 字串}
#   groups       [(class, [連續索引])]，用來把數條 path 包成一個可整組變形的 <g>
ANIMATIONS = {
    "weather-sunny": {
        "root_class": "spin",
        "style": f".spin{{{ORIGIN}animation:spin 8s linear infinite}}"
                 "@keyframes spin{to{transform:rotate(360deg)}}",
    },
}


def baseline_svg(name):
    r = subprocess.run(
        ["git", "show", f"{BASELINE}:instream-weather-icons/assets/{name}.svg"],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"讀不到基準檔 {name}: {r.stderr.strip()}")
    return r.stdout


PATH_RE = re.compile(r"<path\b[^>]*?/>", re.S)


def add_class(tag, cls):
    return re.sub(r"\s*/>\s*$", f' class="{cls}"/>', tag)


def build(name, spec):
    svg = baseline_svg(name)
    paths = PATH_RE.findall(svg)
    parts = PATH_RE.split(svg)
    assert len(parts) == len(paths) + 1, f"{name}: path 切分異常"

    cls_map = spec.get("path_classes", {})
    rendered = [add_class(p, cls_map[i]) if i in cls_map else p
                for i, p in enumerate(paths)]

    open_at, close_at = {}, set()
    for gcls, idxs in spec.get("groups", []):
        assert idxs == list(range(idxs[0], idxs[-1] + 1)), \
            f"{name}: group {gcls} 的索引必須連續"
        open_at[idxs[0]] = gcls
        close_at.add(idxs[-1])

    out = [parts[0]]
    for i, p in enumerate(rendered):
        if i in open_at:
            out.append(f'<g class="{open_at[i]}">')
        out.append(p)
        if i in close_at:
            out.append("</g>")
        out.append(parts[i + 1])
    svg = "".join(out)

    style = f"<style>{REDUCED}{spec['style']}</style>"
    svg = re.sub(r"(<svg\b[^>]*>)", lambda m: m.group(1) + style, svg, count=1)

    if "root_class" in spec:
        svg = re.sub(r'(<g\s+id="[^"]*")',
                     lambda m: m.group(1) + f' class="{spec["root_class"]}"',
                     svg, count=1)

    (ASSETS / f"{name}.svg").write_text(svg)
    return len(paths)


def main():
    targets = sys.argv[1:] or sorted(ANIMATIONS)
    for name in targets:
        if name not in ANIMATIONS:
            raise SystemExit(f"未知的圖示: {name}")
        n = build(name, ANIMATIONS[name])
        print(f"built {name}  ({n} paths)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 執行生成**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-sunny
```

Expected: `built weather-sunny  (9 paths)`

- [ ] **Step 3: 執行驗證，確認通過**

```bash
cd ~/adformate/instream-weather-icons && python3 verify-animations.py weather-sunny
```

Expected: `PASS weather-sunny  frames=4/4 unique`，最後一行 `1/1 passed`

若 frames 只有 1 unique，代表動畫沒跑，多半是 `transform-box:fill-box` 漏掉或 class 沒套上。

- [ ] **Step 4: 目視確認旋轉中心正確**

```bash
cd ~/adformate/instream-weather-icons && for ms in 200 1200 2200; do
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
    --hide-scrollbars --allow-file-access-from-files --virtual-time-budget=$ms \
    --screenshot=/tmp/sunny-$ms.png --window-size=160,160 \
    "file://$PWD/assets/weather-sunny.svg" 2>/dev/null
done; echo "看 /tmp/sunny-200.png /tmp/sunny-1200.png /tmp/sunny-2200.png"
```

Expected: 三張圖的太陽光芒角度不同，且太陽**始終位於畫面正中央**。若太陽跑出畫面或繞著角落轉，代表 `transform-box:fill-box` 沒生效。

- [ ] **Step 5: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-sunny.svg
git commit -m "animate weather-sunny: full-icon rotation

Animated SVGs are regenerated from the static baseline rather than
edited in place, so the build is idempotent and cannot damage geometry.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `weather-overcast` 與 `weather-cloudy`（整朵飄移）

**Files:**
- Modify: `instream-weather-icons/build-animations.py`（新增 2 筆定義）
- Modify: `instream-weather-icons/assets/weather-overcast.svg`、`weather-cloudy.svg`

- [ ] **Step 1: 在 `ANIMATIONS` 加入兩筆定義**

在 `"weather-sunny"` 那筆之後加入：

```python
    "weather-overcast": {
        "root_class": "cloud",
        "style": f".cloud{{{ORIGIN}animation:drift 4s ease-in-out infinite}}" + DRIFT,
    },
    # 與 overcast 同規格但相位錯開，避免兩朵雲在同一畫面上同步擺動
    "weather-cloudy": {
        "root_class": "cloud",
        "style": f".cloud{{{ORIGIN}animation:drift 4s ease-in-out infinite;"
                 "animation-delay:-1.3s}" + DRIFT,
    },
```

- [ ] **Step 2: 生成並驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-overcast weather-cloudy && python3 verify-animations.py weather-overcast weather-cloudy
```

Expected: 兩行 `PASS`，最後 `2/2 passed`

- [ ] **Step 3: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-overcast.svg instream-weather-icons/assets/weather-cloudy.svg
git commit -m "animate weather-overcast and weather-cloudy: horizontal drift

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `weather-rain`（雲靜止、3 滴落下）

**Files:**
- Modify: `instream-weather-icons/build-animations.py`
- Modify: `instream-weather-icons/assets/weather-rain.svg`

- [ ] **Step 1: 加入定義**

雨滴使用**負的** `animation-delay`，讓 `t=0` 時三滴已在不同落下階段，避免開場出現「沒有雨」的空窗。

```python
    "weather-rain": {
        # [0] 雲（不動）、[1][2][3] 雨滴
        "path_classes": {1: "drop d1", 2: "drop d2", 3: "drop d3"},
        "style": f".drop{{{ORIGIN}animation:fall 1.1s linear infinite}}"
                 ".d2{animation-delay:-.37s}.d3{animation-delay:-.73s}" + FALL,
    },
```

- [ ] **Step 2: 生成並驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-rain && python3 verify-animations.py weather-rain
```

Expected: `PASS weather-rain`

- [ ] **Step 3: 目視確認雲沒有跟著動**

```bash
cd ~/adformate/instream-weather-icons && for ms in 200 700 1300; do
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
    --hide-scrollbars --allow-file-access-from-files --virtual-time-budget=$ms \
    --screenshot=/tmp/rain-$ms.png --window-size=160,160 \
    "file://$PWD/assets/weather-rain.svg" 2>/dev/null
done; echo "看 /tmp/rain-200.png /tmp/rain-700.png /tmp/rain-1300.png"
```

Expected: 雨滴位置在三張圖中不同且有淡入淡出，**雲的位置完全不變**。

- [ ] **Step 4: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-rain.svg
git commit -m "animate weather-rain: three staggered falling drops

Negative animation delays keep all three drops mid-flight at t=0 so the
icon never opens on an empty frame.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `weather-thunderstorm`（閃電閃爍 + 4 滴落下）

**Files:**
- Modify: `instream-weather-icons/build-animations.py`
- Modify: `instream-weather-icons/assets/weather-thunderstorm.svg`

- [ ] **Step 1: 加入定義**

閃電以 opacity 基準值 `1` 為主、快速下掉兩次，讀起來是閃動。不使用「平時隱形、偶爾出現」的作法 —— 閃電是圖示的構成元素，消失會讓圖形看起來壞掉。

```python
    "weather-thunderstorm": {
        # [0] 雲（不動）、[1] 閃電、[2]-[5] 雨滴
        "path_classes": {1: "bolt", 2: "drop d1", 3: "drop d2",
                         4: "drop d3", 5: "drop d4"},
        "style": f".drop{{{ORIGIN}animation:fall 1.1s linear infinite}}"
                 ".d2{animation-delay:-.28s}.d3{animation-delay:-.55s}"
                 ".d4{animation-delay:-.83s}" + FALL +
                 ".bolt{animation:flash 2.5s linear infinite}"
                 "@keyframes flash{0%,100%{opacity:1}6%{opacity:.2}"
                 "12%{opacity:1}20%{opacity:.2}28%{opacity:1}}",
    },
```

- [ ] **Step 2: 生成並驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-thunderstorm && python3 verify-animations.py weather-thunderstorm
```

Expected: `PASS weather-thunderstorm`

- [ ] **Step 3: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-thunderstorm.svg
git commit -m "animate weather-thunderstorm: flickering bolt and four drops

The bolt dips in opacity rather than disappearing; it is part of the
icon's silhouette and hiding it makes the glyph look broken.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `weather-sun-shower`（光芒閃爍 + 5 滴落下）

**Files:**
- Modify: `instream-weather-icons/build-animations.py`
- Modify: `instream-weather-icons/assets/weather-sun-shower.svg`

- [ ] **Step 1: 加入定義**

太陽不旋轉。實測顯示光芒群 bbox 中心 `(34.37, 16.29)` 並非太陽真正的圓心，且雲為透空外框 —— 光芒若轉到雲後方會直接穿幫顯示在雲內部。改為各光芒繞自身中心脈動。

```python
    "weather-sun-shower": {
        # [0]-[4] 雨滴、[5]-[9] 光芒、[10] 雲（不動）
        "path_classes": {0: "drop d1", 1: "drop d2", 2: "drop d3",
                         3: "drop d4", 4: "drop d5",
                         5: "ray r1", 6: "ray r2", 7: "ray r3",
                         8: "ray r4", 9: "ray r5"},
        "style": f".drop{{{ORIGIN}animation:fall 1.1s linear infinite}}"
                 ".d2{animation-delay:-.22s}.d3{animation-delay:-.44s}"
                 ".d4{animation-delay:-.66s}.d5{animation-delay:-.88s}" + FALL +
                 f".ray{{{ORIGIN}animation:shimmer 2.4s ease-in-out infinite}}"
                 ".r2{animation-delay:-.48s}.r3{animation-delay:-.96s}"
                 ".r4{animation-delay:-1.44s}.r5{animation-delay:-1.92s}" + SHIMMER,
    },
```

- [ ] **Step 2: 生成並驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-sun-shower && python3 verify-animations.py weather-sun-shower
```

Expected: `PASS weather-sun-shower`

- [ ] **Step 3: 目視確認光芒沒有跑進雲裡**

```bash
cd ~/adformate/instream-weather-icons && for ms in 200 900 1800; do
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
    --hide-scrollbars --allow-file-access-from-files --virtual-time-budget=$ms \
    --screenshot=/tmp/sunshower-$ms.png --window-size=200,200 \
    "file://$PWD/assets/weather-sun-shower.svg" 2>/dev/null
done; echo "看 /tmp/sunshower-*.png"
```

Expected: 光芒在原位明暗縮放，**不位移、不進入雲的輪廓內**。

- [ ] **Step 4: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-sun-shower.svg
git commit -m "animate weather-sun-shower: shimmering rays and five drops

Rays pulse in place rather than orbiting. Measured ray-group bbox centre
is not the sun's true centre, and the cloud is a hollow outline, so an
orbit would visibly pass through the cloud interior.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `weather-partly-cloudy`（光芒閃爍 + 雲飄）

**Files:**
- Modify: `instream-weather-icons/build-animations.py`
- Modify: `instream-weather-icons/assets/weather-partly-cloudy.svg`

- [ ] **Step 1: 加入定義**

```python
    "weather-partly-cloudy": {
        # [0]-[3] 光芒、[4] 雲
        "path_classes": {0: "ray r1", 1: "ray r2", 2: "ray r3",
                         3: "ray r4", 4: "cloud"},
        "style": f".ray{{{ORIGIN}animation:shimmer 2.4s ease-in-out infinite}}"
                 ".r2{animation-delay:-.6s}.r3{animation-delay:-1.2s}"
                 ".r4{animation-delay:-1.8s}" + SHIMMER +
                 f".cloud{{{ORIGIN}animation:drift 4s ease-in-out infinite}}" + DRIFT,
    },
```

- [ ] **Step 2: 生成並驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-partly-cloudy && python3 verify-animations.py weather-partly-cloudy
```

Expected: `PASS weather-partly-cloudy`

- [ ] **Step 3: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-partly-cloudy.svg
git commit -m "animate weather-partly-cloudy: shimmering rays and drifting cloud

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `weather-snow`（3 片雪花飄落自轉）

**Files:**
- Modify: `instream-weather-icons/build-animations.py`
- Modify: `instream-weather-icons/assets/weather-snow.svg`

- [ ] **Step 1: 加入定義**

這是唯一需要用到 `groups` 的圖示 —— 每片雪花由 3 條筆劃（`—` `\` `/`）組成，必須包成一個 `<g>` 才能整片一起旋轉。

```python
    "weather-snow": {
        # 3 片雪花，每片 3 筆劃。實測中心：
        #   f1 (40.00, 25.79) / f2 (55.02, 52.21) / f3 (24.98, 52.21)
        "groups": [("flake f1", [0, 1, 2]),
                   ("flake f2", [3, 4, 5]),
                   ("flake f3", [6, 7, 8])],
        "style": f".flake{{{ORIGIN}animation:snowdrift 3s ease-in-out infinite}}"
                 ".f2{animation-delay:-1s}.f3{animation-delay:-2s}"
                 "@keyframes snowdrift{"
                 "0%{transform:translateY(-3px) rotate(0deg);opacity:.8}"
                 "50%{transform:translateY(3px) rotate(180deg);opacity:1}"
                 "100%{transform:translateY(-3px) rotate(360deg);opacity:.8}}",
    },
```

- [ ] **Step 2: 生成並驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-snow && python3 verify-animations.py weather-snow
```

Expected: `PASS weather-snow`

- [ ] **Step 3: 目視確認每片雪花繞自己的中心轉**

```bash
cd ~/adformate/instream-weather-icons && for ms in 200 1000 2000; do
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
    --hide-scrollbars --allow-file-access-from-files --virtual-time-budget=$ms \
    --screenshot=/tmp/snow-$ms.png --window-size=200,200 \
    "file://$PWD/assets/weather-snow.svg" 2>/dev/null
done; echo "看 /tmp/snow-*.png"
```

Expected: 三片雪花各自在原位旋轉並小幅上下浮動。**三片不得互相靠攏或分離** —— 若有，代表 group 包錯，某片雪花的筆劃被拆到別組。

- [ ] **Step 4: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-snow.svg
git commit -m "animate weather-snow: three flakes drifting and rotating

Each flake is three separate strokes, so they are wrapped in a group to
rotate as one shape.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: `weather-fog`（9 條霧線飄移）

**Files:**
- Modify: `instream-weather-icons/build-animations.py`
- Modify: `instream-weather-icons/assets/weather-fog.svg`

- [ ] **Step 1: 加入定義**

9 條線各自獨立，延遲依序錯開，製造出層次不一的飄移感。

```python
    "weather-fog": {
        "path_classes": {i: f"fogline m{i + 1}" for i in range(9)},
        "style": f".fogline{{{ORIGIN}animation:mist 5s ease-in-out infinite}}"
                 ".m2{animation-delay:-.5s}.m3{animation-delay:-1s}"
                 ".m4{animation-delay:-1.5s}.m5{animation-delay:-2s}"
                 ".m6{animation-delay:-2.5s}.m7{animation-delay:-3s}"
                 ".m8{animation-delay:-3.5s}.m9{animation-delay:-4s}"
                 "@keyframes mist{0%,100%{transform:translateX(-4px)}"
                 "50%{transform:translateX(4px)}}",
    },
```

- [ ] **Step 2: 生成並驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py weather-fog && python3 verify-animations.py weather-fog
```

Expected: `PASS weather-fog`

- [ ] **Step 3: Commit**

```bash
cd ~/adformate && git add instream-weather-icons/build-animations.py instream-weather-icons/assets/weather-fog.svg
git commit -m "animate weather-fog: nine mist lines drifting at staggered phases

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: 全套驗證與 `index.html` 整合確認

**Files:**
- 無修改，僅驗證

- [ ] **Step 1: 從基準完整重建全部 9 顆**

驗證 build 腳本可重複執行且結果一致。

```bash
cd ~/adformate/instream-weather-icons && python3 build-animations.py && git status --short assets/
```

Expected: `built ...` 共 9 行。`git status` 對 `assets/` **不應有任何輸出** —— 若有，代表重建結果與已 commit 的不一致，build 不是冪等的。

- [ ] **Step 2: 全套驗證**

```bash
cd ~/adformate/instream-weather-icons && python3 verify-animations.py
```

Expected: 9 行 `PASS`，最後一行 `9/9 passed`

- [ ] **Step 3: 確認非天氣的 12 顆完全沒被動到**

```bash
cd ~/adformate && git diff --stat abc40ee -- instream-weather-icons/assets/ | grep -v '^ weather-' | head
```

Expected: 只列出 `weather-*.svg` 共 9 個檔案的變更摘要，不得出現 `aqi-*`、`humidity-*`、`temperature`、`uv`、`umbrella`。

- [ ] **Step 4: 在 `index.html` 的 `<img>` 情境下確認動畫會跑**

這是最終驗收 —— 直接開 `.svg` 與透過 `<img>` 載入的 CSS 執行環境不同，前者過不代表後者會過。

```bash
cd ~/adformate/instream-weather-icons && for ms in 300 1500 3000; do
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
    --hide-scrollbars --allow-file-access-from-files --virtual-time-budget=$ms \
    --screenshot=/tmp/page-$ms.png --window-size=1440,700 \
    "file://$PWD/index.html" 2>/dev/null
done
python3 -c "
import hashlib,pathlib
h=[hashlib.sha256(pathlib.Path(f'/tmp/page-{m}.png').read_bytes()).hexdigest()[:12] for m in (300,1500,3000)]
print('hashes:', h)
print('PASS —— 頁面有動' if len(set(h))>1 else 'FAIL —— 頁面三個時間點完全相同')
"
```

Expected: `PASS —— 頁面有動`，且 `/tmp/page-*.png` 目視檢查時天氣列的 9 顆圖示形狀正常、沒有變形或跑位。

- [ ] **Step 5: Commit（若前述步驟有任何修正）**

```bash
cd ~/adformate && git status --short
```

若無變更則跳過。若有修正：

```bash
git add -A instream-weather-icons/
git commit -m "fix animation issues found during integration verification

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## 完成後

分支 `weather-icon-animation` 應包含：靜態基準、spec、驗證腳本、生成腳本、9 個動畫圖示。

`index.html` 全程未修改 —— 這是選擇「動畫內嵌於 SVG」方案的核心驗證：資產可直接搬到任何 creative 使用。
