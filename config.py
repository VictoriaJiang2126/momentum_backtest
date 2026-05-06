from pathlib import Path

MARKET_FILTER = "SPY"  # 大盘代理

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)

# 时间范围（多1年预热期供 SMA200 / 52w high 用）
START = "2023-01-01"
END = "2026-12-01"
BACKTEST_START = "2024-01-01"  # 实际回测从这天开始

# 组合参数
INIT_CASH = 100_000
POS_SIZE = 0.20 #每个占比
MAX_POS = 5 #共几只股票
FEE = 0.0001

# 入场筛选
MIN_PRICE = 5.0
MIN_AVG_VOL = 500_000
NEAR_HIGH_PCT = 0.10
WEEKLY_MIN, WEEKLY_MAX = 0.10, 0.30
RVOL_MIN = 2.0

# 出场规则
STOP_LOSS = 0.07
TRAIL_DD = 0.10
EXIT_SMA = 10
MAX_HOLD = 30
