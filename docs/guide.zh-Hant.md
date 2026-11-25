# BTC 報價與穩定幣研究

本專案使用 2023 年 3 月 1 至 21 日的 UTC 分鐘行情，比較 BTC 在 USD、USDC 和 USDT 市場的報價。用隨附的六份市場快照可以離線重建五份 CSV 及報告的八張圖。

GitHub 收錄六份原始行情、研究報告、八張圖、統計摘要及資料品質表。三份較大的分鐘明細可用下列離線指令重建，Git 會自動忽略這些衍生 CSV。[English overview](../README.md)

## 安裝與重現

在專案根目錄使用 Python 3.12 和獨立虛擬環境。Windows PowerShell 指令如下。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m iaqf --offline
.\.venv\Scripts\python -m unittest discover -s tests -v
```

macOS 或 Linux 可用 `python3.12 -m venv .venv` 建立環境，並用 `.venv/bin/python` 執行後三個指令。安裝一次後，測試及使用隨附快照的分析均可離線執行。啟用虛擬環境後也可使用 `iaqf-study --offline`。若 Windows 應用程式控制攔截安裝器產生的命令列啟動檔，使用上方的 Python 模組入口即可。原先的 `pip install -r requirements.txt` 與 `python main.py --offline` 會使用同一套設定和入口。

預設讀取 `data/raw/`，將結果寫入 `results/`。使用可編輯安裝時，預設路徑以這份專案為準。只安裝程式 wheel 時，請從含有研究資料的目錄執行，或明確指定路徑。例如 `python -m iaqf --offline --data-dir ./data/raw --output-dir ./new-results`。省略 `--offline` 時，流程只向交易所補取缺少的交易對。重現本報告請使用隨附快照。

## 目錄

```text
iaqf-stablecoin-research/
├── pyproject.toml              套件、版本、依賴、CLI 與 Ruff 設定
├── src/iaqf/
│   ├── cli.py                  命令列參數與結束狀態
│   ├── config.py               市場清單、UTC 期間、路徑與費率假設
│   ├── data/                   CCXT 下載、K 線與資料品質檢查
│   ├── analysis/               分鐘對齊、報價差、分期統計
│   ├── reporting/              畫圖與圖表定義
│   ├── utils/                  共用 CSV 寫入、UTC 時間與觀測標記
│   └── workflow/
│       ├── pipeline.py         串接五個步驟
│       ├── publication.py      發布完整結果及還原失敗的寫入
│       └── steps/              acquire → validate → prepare → analyze → report
├── data/raw/                   六份隨附的市場快照
├── results/
│   ├── tables/                 資料品質、對齊後的輸入、分析明細與摘要
│   └── figures/                圖 1 至圖 8，依主報告圖號命名
├── reports/                    Word 與 PDF 主報告
│   └── supplement/             原附的獨立策略研究文件
└── tests/
    ├── unit/                   資料、計算與寫入行為
    └── integration/            CLI 與整個工作流程
```

## 一次執行會做什麼

| 步驟 | 模組 | 職責及產物 |
| --- | --- | --- |
| 1. 取得資料 | `workflow/steps/acquire.py` | 比對設定的市場清單。離線模式一次列出缺檔，線上模式重用每個交易所的下載器。 |
| 2. 檢查資料 | `workflow/steps/validate.py` | 檢查時間戳、重複分鐘、OHLCV 及資料來源標記，寫出 `missing_report.csv`。結構錯誤會中止流程並保留診斷表。 |
| 3. 準備輸入 | `workflow/steps/prepare.py` | 對齊六個市場，從同一份資料產出價格概覽 `basis_output.csv` 和可供重跑的 `q1_basis_dataset.csv`。 |
| 4. 計算基差 | `workflow/steps/analyze.py` | 使用已保存的對齊資料計算每分鐘的基差、費率門檻及報酬，寫出 `q1_analysis_output.csv`。 |
| 5. 產出報告數據 | `workflow/steps/report.py` | 使用同一份分析明細，產出分期統計 `q1_summary.csv` 及八張圖。 |

`DataDownloader` 管理同一個交易所的客戶端與目的路徑。`DataValidator` 管理研究期間的預期分鐘格，供六個市場共用。`BasisComparison` 將每項基差的左右報價、分母及費率放在同一個不可變物件裡。對齊分鐘、分期和統計摘要使用可單獨測試的函式。各步驟透過函式參數傳遞檔案路徑或資料表，工作流程負責順序與發布。

## 指標與樣本

相對基差為 `(左側 BTC 報價 − 右側 BTC 報價) / 右側 BTC 報價`。明細中的 `pct_basis_*` 是小數，例如 0.01 表示 1%。摘要中標為 `_pct` 的欄位已換算為百分數。每組基差只使用同一 UTC 分鐘內兩邊都有正成交量、有效正價格的資料，缺值代表該分鐘無法比較。舊快照缺乏補值標記，新下載的資料會透過 `is_observed` 區分交易所回應與程式補入的分鐘。

費率門檻採兩筆假設 taker 費用之和。Binance.US 與 Coinbase 為 0.70%，Bitstamp 與 Coinbase 為 1.00%，兩筆 Binance.US 為 0.20%，兩筆 Bitstamp 為 0.80%。摘要的超標比例以可比較的分鐘數為分母。資料只含 K 線，無法從門檻超標推算已扣除買賣價差及滑價的收入。

## 核對報告的結論

以下程式從明細選出 3 月 10 至 12 日六個市場同時有成交的 499 個分鐘，再分別計算 Bitstamp 的 USDC 對 USD、Binance.US 的 USDT 對 USDC，以及 Binance.US 的 USDT 對 Coinbase 的 USD 三項 BTC 報價基差。結果四捨五入後應為 +1.66%、−3.15%、−0.57%。

```python
import pandas as pd

minutes = pd.read_csv("results/tables/q1_analysis_output.csv")
markets = ["cb_usd", "cb_usdc", "bs_usd", "bs_usdc", "bu_usdt", "bu_usdc"]
bases = ["pct_basis_usdc_usd_bitstamp", "pct_basis_usdt_usdc", "pct_basis_usdt_usd"]
matched = minutes.loc[minutes["regime"].eq("stress")].dropna(subset=markets)
print(len(matched))
print(matched[bases].median().mul(100).round(2))
```

## 工程參考

- 套件從 `src/` 安裝，命令列、測試與外部 Python 程式使用相同匯入路徑。依賴與命令列入口集中在 `pyproject.toml`。[PyPA 套件配置](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) · [PyPA 專案設定](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- 函式說明記錄輸入限制、單位及錯誤處理。測試使用標準函式庫的測試探索、臨時目錄與模擬客戶端。[PEP 257](https://peps.python.org/pep-0257/) · [Python unittest](https://docs.python.org/3/library/unittest.html)
- OHLCV 欄位順序與時間單位遵循 CCXT 的介面。[CCXT 行情資料手冊](https://github.com/ccxt/ccxt/wiki/Manual#ohlcv-candlestick-charts)
