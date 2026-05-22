# 艾略特波浪理論 (Elliott Wave Principle) 終極量化交易演算法需求書 v2.0

## 1. 系統架構與數據預處理 (System Architecture & Data Preprocessing)

### 1.1 多時間框架分析 (Multi-Timeframe Analysis, MTFA)
艾略特波浪理論的核心是「分形幾何 (Fractal Geometry)」，波浪的級數可變，形狀不變。演算法必須同時監控至少 3 個時間框架來確認大、中、小趨勢。
*   **數據獲取 (Data Feed)**：需拉取不同週期的 OHLCV 數據。
*   **刻度選擇 (Scale)**：
    *   **長期/大波幅分析**：當波幅超過 20% 時，必須使用**半對數刻度 (Semi-logarithmic Scale)** 計算價格通道和目標價。
    *   **短期/小波幅分析**：大浪級以下或日線/60分鐘線，使用**算術刻度 (Arithmetic Scale)**。
*   **波浪級別映射 (Wave Degree Mapping)**：
    *   `Primary (大浪)`：對應 **週線圖 (Weekly)** 或 **月線圖 (Monthly)**。
    *   `Intermediate (中浪)`：對應 **日線圖 (Daily)**。
    *   `Minor / Minute (小浪/細浪)`：對應 **60 分鐘線 (Hourly)**。這是實戰中最適合進行波浪細微劃分的時間週期。

## 2. 核心約束條件：三大鐵律與例外 (Absolute Rules & Exceptions)

### 2.1 推動浪 (Motive Wave - 1, 3, 5, A, C) 核心鐵律 (Hard Constraints)
在任何正常的 5 浪推動結構中，必須 `100%` 滿足以下條件，否則立即使當前計數失效並重置：
*   **鐵律 1**：浪 2 的回撤絕對不能超過浪 1 的起點。
    *   *邏輯*：`If Trend == UP: Low(Wave 2) >= Start(Wave 1)`
*   **鐵律 2**：浪 3 永遠不能是浪 1、3、5 中最短的一浪。
    *   *邏輯*：`Length(Wave 3) > min(Length(Wave 1), Length(Wave 5))`
*   **鐵律 3**：浪 4 的最低點（或最高點）絕對不能進入浪 1 的價格範圍。
    *   *邏輯*：`If Trend == UP: Low(Wave 4) > High(Wave 1)`

### 2.2 鐵律的唯一例外：傾斜三角形 (Diagonal Triangles)
演算法必須設立特例捕捉傾斜三角形，此時 **浪 4 允許與 浪 1 重疊 (Overlap)**。
*   **引導傾斜三角形 (Leading Diagonal)**：只出現在浪 1 或浪 A。內部結構為 `5-3-5-3-5`。
*   **終結傾斜三角形 (Ending Diagonal)**：只出現在浪 5 或浪 C。內部結構為 `3-3-3-3-3`，通常伴隨成交量縮減。
    *   *突破特徵*：通常會發生「翻越 (Throw-over)」，即浪 5 短暫刺穿趨勢線後迅速反轉。

## 3. 波浪形態詳細分類引擎 (Wave Pattern Classification Engine)

### 3.1 推動浪的變體 (Motive Wave Variations)
*   **延長浪 (Extensions)**：多數推動浪會有一個延長浪（通常是浪 3）。如果浪 3 延長，浪 1 和浪 5 傾向於等長或成 0.618 比例。
*   **衰竭 / 失敗的第5浪 (Truncation)**：浪 5 必須包含 5 個子浪，但未能突破浪 3 的終點。通常在極強的浪 3 後出現。

### 3.2 調整浪分類 (Corrective Waves - 2, 4, B)
調整浪極度複雜，Agent 需利用以下邏輯判定：
*   **鋸齒型 (Zigzag, 5-3-5)**：
    *   浪 B 高點明顯低於浪 A 起點。浪 C 必須創低（牛市中）。
    *   可變體為雙重或三重鋸齒型 (W-X-Y)。
*   **平台型 (Flat, 3-3-5)**：
    *   **普通平台 (Regular)**：浪 B 接近浪 A 起點，浪 C 略微跌破浪 A 終點。
    *   **擴散平台 (Expanded)**：浪 B 超過浪 A 起點（牛市中創新高），浪 C 遠低於浪 A 終點。
    *   **順勢平台 (Running)**：極罕見，浪 B 大幅超過浪 A 起點，浪 C 未能達到浪 A 終點。
*   **三角形 (Triangle, 3-3-3-3-3)**：
    *   通常出現在浪 4 或浪 B。
    *   分為：收縮 (Contracting)、擴散 (Expanding)、上升 (Ascending)、下降 (Descending)。
    *   *操作邏輯*：三角形突破後，通常只剩最後一波推動浪（浪 5 ），其突破幅度通常等同於三角形的最寬距離。

## 4. 評分與驗證指南 (Guidelines & Scoring System - Soft Constraints)
滿足鐵律後，根據以下指南進行評分 (Weighting)，分數越高的波浪劃分越可能正確：

*   **交替原則 (Rule of Alternation) (Weight: 高)**：
    *   如果浪 2 是劇烈調整（如鋸齒型，深度回撤），浪 4 大概率是橫盤調整（平台型、三角形，淺幅回撤）。反之亦然。
*   **調整浪的深度 (Depth of Corrective Waves) (Weight: 中)**：
    *   調整浪（特別是浪 4）通常會在前一小級的浪 4 價格範圍內結束。
*   **通道技術 (Channeling) (Weight: 高)**：
    *   畫一條線連接浪 1 和浪 3 終點，再畫一條平行線穿過浪 2 終點，這可以預測浪 4 終點。
    *   當浪 4 結束，連接浪 2 和 4 終點，並畫平行線穿過浪 3 終點，可預測浪 5 目標價。
*   **成交量驗證 (Volume) (Weight: 高)**：
    *   浪 3 期間成交量應顯著放大。
    *   浪 5 成交量通常低於浪 3（除非浪 5 發生延長）。成交量在三角形調整中必須逐漸遞減。

## 5. 斐波納奇數學目標價模組 (Fibonacci Mathematics & Price Targets)

Agent 必須計算以下斐波納奇比率來設定 Limit Orders：

*   **回撤比率 (Retracements)**：
    *   **浪 2** 通常回撤浪 1 的 **61.8%** 或 **50%**。
    *   **浪 4** 通常回撤浪 3 的 **38.2%**。
*   **倍數/映射比率 (Multiples/Projections)**：
    *   **浪 3 目標**：通常為浪 1 長度的 **1.618 倍** 或 **2.618 倍**。
    *   **浪 5 目標** (若浪 3 已延長)：浪 5 往往等於浪 1 的長度，或浪 1 至浪 3 總長度的 **0.618 倍**。
    *   **浪 C 目標** (鋸齒型中)：浪 C 長度通常等於浪 A，或浪 A 的 **1.618 倍**。

## 6. 具體交易情境與執行邏輯 (Trading Situations & Execution Logic)
*注意：以下以做多 (Long) 為例，做空 (Short) 邏輯反轉即可。*

### 🟢 交易情境 A：捕捉最具爆發力的 浪 3 (Catching Wave 3)
*   **狀態確認**：大級別處於上升趨勢，60分鐘線識別出浪 1 完成，正在運行浪 2。
*   **進場條件 (Entry)**：
    1.  浪 2 達到浪 1 的 50% 或 61.8% 斐波納奇回撤位。
    2.  在低時間框架（如 15 分鐘）出現底部分型或看漲 K 線反轉。
    3.  *(保守做法)*：等待價格突破浪 1 的高點。
*   **止損 (Stop Loss)**：嚴格設置在 **浪 1 的起點**（若跌破則鐵律 1 失敗，計數錯誤）。
*   **止盈 (Take Profit)**：分批平倉。
    *   TP1：浪 1 的 1.618 倍目標位。
    *   TP2：浪 1 的 2.618 倍目標位。

### 🟢 交易情境 B：捕捉最後的派發 浪 5 (Catching Wave 5)
*   **狀態確認**：浪 3 已確認（且不是最短），目前處於浪 4 盤整。
*   **進場條件 (Entry)**：
    1.  浪 4 滿足交替原則（如浪 2 是急跌，浪 4 是平台型橫盤）。
    2.  浪 4 回落到浪 3 的 38.2% 區域，且進入了上一級別子浪 4 的領地。
    3.  價格觸及由浪 1-3 與 浪 2 連接構造的下降通道下沿。
*   **止損 (Stop Loss)**：嚴格設置在 **浪 1 的頂點**（若跌入浪 1 範圍則違反鐵律 3）。
*   **止盈 (Take Profit)**：
    *   TP1：結合趨勢通道的上沿。
    *   TP2：浪 1 至浪 3 總長度的 0.618 倍處。
    *   *監控退出*：若突破時成交量未跟上，且發生 RSI 背離，隨時準備因「第五浪衰竭」提早手動平倉。

### 🔴 交易情境 C：三角形突破捕捉 (Trading the Triangle Breakout)
*   **狀態確認**：識別出 a-b-c-d-e 5波收斂/擴散結構，通常發生在浪 4 或浪 B。
*   **進場條件 (Entry)**：當價格突破 a-c 趨勢線或 b-d 趨勢線時。
*   **止損 (Stop Loss)**：設置在三角形最後一個點（浪 e）的極值。
*   **止盈 (Take Profit)**：測量三角形最寬處的高度（通常是浪 a 的高低點差），從突破點等距向上/向下映射（Thrust Measurement）。

## 7. 開發者/Agent 實施要求 (Implementation Constraints for Agent)
1.  **OOP 結構 (Object-Oriented Programming)**：將每個「Wave」定義為一個 Object，包含屬性：`Start_Price`, `End_Price`, `Time_Duration`, `Volume`, `Wave_Degree`。
2.  **狀態機 (State Machine)**：系統需維護當前的 `Market_State` (例如：`Searching_Wave_2`, `In_Wave_3_Impulse`)。
3.  **回溯算法 (Backtracking Algorithm)**：由於「千人千浪」，Agent 必須具備重新標記 (Re-labeling) 能力。當硬約束（三大鐵律）被觸發破壞時，自動回退到上一個 Pivot 節點，重新計算最有可能的次優波浪組合。
4.  **模塊化測試 (Unit Testing)**：必須為「三大鐵律」和「交替原則」編寫單獨的測試用例，輸入虛擬 K 線數據，確保判定邏輯 100% 準確。
```
## 8. 進階補充模組：複雜形態與時間量化 (Advanced Modules & Time Quant)

### 8.1 複雜/聯合型調整浪 (Complex / Combination Corrective Waves)
真實市場中，簡單的 A-B-C 調整往往不夠用，系統必須能夠識別**聯合型調整浪 (Combinations)**。
*   **W-X-Y 結構 (雙重三浪/雙重鋸齒型)**：當一個簡單調整浪（W）未能達到足夠的價格或時間目標時，市場會透過一個反作用浪（X）連接另一個調整浪（Y）。
*   **W-X-Y-X-Z 結構 (三重三浪/三重鋸齒型)**：極端情況下的橫盤或深度調整。
*   **Agent 實作邏輯**：當系統發現一個 A-B-C 結構完成後，趨勢仍未反轉且進入橫盤，必須啟動 `Combination_Mode`，將先前的 A-B-C 降級標記為浪 W，並開始尋找 X 浪（反彈）和 Y 浪。

### 8.2 調整浪深度的精確錨點 (Precise Depth of Corrective Waves)
除了斐波納奇回撤比率，原著提供了一個極高機率的支撐/阻力錨點：
*   **規則**：一個調整浪（特別是第 4 浪），其最大回撤幅度通常會落在**「前一小級別的第 4 浪」**的價格區域內。
*   **Agent 實作邏輯**：當計算大一級別的浪 4 的 `Buy Limit Order` 時，除了計算浪 3 的 38.2% 回撤，**必須**同時讀取浪 3 內部的子浪 (iv) 的價格區間。這兩個價格區間的重疊處，即為最高勝率的進場 Zone。

### 8.3 波浪個性的技術指標量化 (Quantifying Wave Personality)
Agent 不能只看價格，必須將書中提到的「波浪個性」與現代技術指標（如 RSI, MACD, OBV）結合驗證：
*   **浪 2 (極度悲觀)**：通常回撤極深，此時 RSI 應處於極度超賣區（< 30），且成交量明顯萎縮。
*   **浪 3 (強勁爆發)**：市場參與度最高。此時 RSI 必須突破超買區（> 70），且 MACD 柱狀圖必須創下整個循環的最高/最低點。
*   **浪 5 (背離與派發)**：雖然價格創出新高（或新低），但內部動能衰竭。
    *   **Agent 實作邏輯**：如果 `Price(Wave 5) > Price(Wave 3)`，但 `RSI(Wave 5) < RSI(Wave 3)` 或 `MACD(Wave 5) < MACD(Wave 3)`（即技術指標頂背離/底背離），這就是確認浪 5 結束的核心信號，應立即觸發 `Take Profit` 或 `Short` 訊號。

### 8.4 斐波納奇時間序列預測 (Fibonacci Time Sequences)
波浪理論不僅預測價格，也預測時間（雖然準確度次於價格，但可作匯聚點確認）。
*   **時間週期測量**：市場的重要頂部與底部轉折點，其相隔的交易日或週期數，經常符合斐波納奇數列（如 8, 13, 21, 34, 55, 89）。
*   **Agent 實作邏輯**：編寫一個 `TimeCycle_Projections` 函數。當浪 1 或浪 3 開始時，向右映射 13, 21, 34 根 K 線的時間窗 (Time Windows)。如果價格剛好在這些斐波納奇時間窗內到達了斐波納奇價格目標，該交易訊號的 `Confidence_Score` 大幅加權。