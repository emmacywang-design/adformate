# 天氣圖示 SVG 內嵌動畫

日期：2026-09-14
分支：`weather-icon-animation`
靜態基準：`abc40ee`

## 目標

讓 `instream-weather-icons/assets/` 裡的 9 顆天氣圖示動起來，動態要符合各自的物理語意（太陽旋轉、雨滴落下、閃電閃爍），而非統一套用單一轉場效果。

## 範圍

**納入**：天氣 9 顆
`weather-sunny`、`weather-partly-cloudy`、`weather-overcast`、`weather-cloudy`、`weather-rain`、`weather-sun-shower`、`weather-thunderstorm`、`weather-snow`、`weather-fog`

**不納入**：AQI 6 顆、`temperature`、`humidity-0/50/100`、`uv`、`umbrella`
理由：表情圖示與溫濕度計是狀態指示，持續動態會干擾閱讀。待天氣組完成、看過實際效果後再決定是否擴充。

## 實作方式

動畫以 `<style>` + `@keyframes` **內嵌在每個 `.svg` 檔案內部**，path 加上語意化 class。

選此方案的理由：
- 資產可攜 — `.svg` 丟到任何 creative、頁面或 CSS background 都會動
- 現有 `index.html` 的 `<img src="...">` 標記完全不用改
- inStream 廣告情境沒有 hover，不需要外部觸發控制

已知代價：外部無法控制播放（不能 hover 觸發、不能暫停、不能即時調速）。若日後需要互動控制，得另外做 inline 版本。

## 動態規格

動態個性：**明顯可辨識** — 一眼看得出在動，但不到喧賓奪主。

| Icon | 動態 | 規格 |
|---|---|---|
| `sunny` | 整顆旋轉 | `rotate 360°` / `8s` / `linear` |
| `partly-cloudy` | 光芒繞太陽轉 + 雲飄 | 光芒 `rotate 360°` / `8s`；雲 `translateX ±3px` / `4s` / `ease-in-out` |
| `overcast` | 整朵飄 | `translateX ±3px` / `4s` / `ease-in-out` |
| `cloudy` | 整朵飄 | 同 `overcast`，加 `animation-delay: -1.3s` 錯開相位 |
| `rain` | 雲靜止、3 滴落下 | 雨滴向下位移 `16px` / `1.1s`；delay `0` / `.25s` / `.5s` |
| `sun-shower` | 太陽轉 + 5 滴落下 | 太陽 `8s`；雨滴 `1.1s`，每滴 delay 遞增 `.2s` |
| `thunderstorm` | 閃電雙閃 + 4 滴落下 | 閃電 `opacity` 雙閃 / `2.5s`；雨滴同 `rain` |
| `snow` | 雪花飄落 + 自轉 | 每朵 `translateY` + `rotate` / `3s`，相位錯開 |
| `fog` | 霧線水平飄移 | 各線 `translateX ±4px` / `5s`，速度略異製造層次 |

雨滴與雪花的循環必須搭配 `opacity` 在終點淡出、起點淡入。純位移循環會出現「瞬間跳回起點」的破綻。

## 技術要點

**旋轉原點**
SVG 元素的 CSS `transform-origin` 預設為 viewport 左上角 `(0,0)`。直接寫 `rotate()` 會讓元素繞畫布左上角公轉，而非自轉。所有旋轉元素必須設定：

```css
transform-box: fill-box;
transform-origin: center;
```

**只用 `transform` 與 `opacity`**
不依賴任何外部資源（字型、圖片、JS）。這是 `<img>` 載入 SVG 時動畫能正常執行的前提。

**`prefers-reduced-motion`**
每個檔案加入：

```css
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; }
}
```

系統開啟「減少動態」時回退為靜態圖。若日後需要廣告素材無條件播放，刪除此區塊即可。

## path 分離度盤點

已透過 bounding box 分析確認：

| Icon | 結構 | 狀態 |
|---|---|---|
| `rain` | 1 雲 + 3 雨滴（各 7.5×11.4） | 可分離 |
| `thunderstorm` | 1 雲 + 1 閃電（11.2×26.3）+ 4 雨滴 | 可分離 |
| `sun-shower` | 5 雨滴 + 太陽組 + 1 雲 | 可分離 |
| `partly-cloudy` | 1 雲 + 4 條光芒 | 可分離 |
| `sunny` | 9 條疊合弧線 | 拆不乾淨，改為整顆旋轉（放射對稱，視覺等價） |
| `cloudy` / `overcast` | 單一 path | 僅能整朵位移，符合規格需求 |
| `snow` / `fog` | 9 條，bbox 互相重疊 | **待確認** |

`snow` 與 `fog` 的 bounding box 估算不可靠（路徑含弧線指令，會使座標解析失準）。實作時必須逐條單獨渲染，確認每條 path 對應哪片雪花／哪條霧線後再分組，不得憑座標猜測。

## 驗證方式

1. **逐條渲染** — `snow`、`fog` 的每條 path 單獨輸出，確認分組正確
2. **多時間點截圖** — 以 Chrome headless `--virtual-time-budget` 在動畫週期的不同時間點取樣，確認畫面確實改變。只截第一幀無法證明動畫有在跑
3. **`<img>` 情境驗證** — 必須透過 `index.html` 的 `<img src>` 驗證，不可只用瀏覽器直接開 `.svg`。兩者的 CSS 執行環境不同
4. **回歸檢查** — 確認 9 顆的靜態外觀（形狀、位置、尺寸）與基準 `abc40ee` 一致，動畫不得改變圖形本身

## 風險

- **改寫原檔**：動畫直接寫入 `assets/*.svg`，靜態版僅存在於 commit `abc40ee`。Figma 匯出網址已於下載後 7 天失效，無法重新取得
- **`fill="white"` 硬編碼**：既有問題，本次不處理。動畫不會使其惡化
- **檔案膨脹**：每檔約增加 400~600 bytes
