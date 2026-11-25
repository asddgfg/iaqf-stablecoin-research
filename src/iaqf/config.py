"""Define the study's market universe, dates, output locations and fee assumptions."""

from pathlib import Path


def default_project_dir() -> Path:
    """Return the source checkout, or the launch directory for an installed wheel.

    A source checkout keeps the sample data next to pyproject.toml. A wheel
    installs code in site-packages, so its data and results belong to the
    workspace from which the user launches the workflow.
    """
    source_dir = Path(__file__).resolve().parent.parent
    if source_dir.name == "src" and (source_dir.parent / "pyproject.toml").is_file():
        return source_dir.parent
    return Path.cwd()


PROJECT_DIR = default_project_dir()
DATA_DIR = PROJECT_DIR / "data" / "raw"
RESULTS_DIR = PROJECT_DIR / "results"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
START_DATE = "2023-03-01T00:00:00Z"
END_DATE = "2023-03-21T23:59:00Z"  # The candle starting at this minute is included.
TIMEFRAME = "1m"
MINUTE_MS = 60_000
PRICE_COLUMNS = ["open", "high", "low", "close"]
CANDLE_COLUMNS = ["timestamp", *PRICE_COLUMNS, "volume"]
# All three venue adapters accept this page size, including Coinbase's limit.
LIMIT = 300

# Field order is part of the published CSV schema. Keep quote aliases, venue
# names and instruments together so adding a market requires one catalog edit.
_MARKET_BOOKS = {
    "cb_usd": ("coinbase", "BTC/USD"),
    "cb_usdc": ("coinbase", "BTC/USDC"),
    "bs_usd": ("bitstamp", "BTC/USD"),
    "bs_usdc": ("bitstamp", "BTC/USDC"),
    "bu_usdt": ("binanceus", "BTC/USDT"),
    "bu_usdc": ("binanceus", "BTC/USDC"),
}


def market_filename(exchange_name: str, symbol: str) -> str:
    """Return the study's canonical CSV filename for a CCXT spot symbol."""
    base, quote = symbol.split("/")
    if not all(part.isalnum() for part in (exchange_name, base, quote)):
        raise ValueError(f"Invalid spot market name: {exchange_name} {symbol}")
    return f"{exchange_name}_{base}_{quote}.csv"


def _pairs_by_exchange(books: dict[str, tuple[str, str]]) -> dict[str, tuple[str, ...]]:
    """Group study symbols by venue so one rate-limited client serves each group."""
    grouped: dict[str, list[str]] = {}
    for venue, symbol in books.values():
        grouped.setdefault(venue, []).append(symbol)
    return {venue: tuple(symbols) for venue, symbols in grouped.items()}


MARKETS = {alias: market_filename(*book) for alias, book in _MARKET_BOOKS.items()}
PAIRS = _pairs_by_exchange(_MARKET_BOOKS)


# Taker fees are historical scenario inputs, expressed as fractions of notional.
FEE_COINBASE = 0.006
FEE_BITSTAMP = 0.004
FEE_BINANCEUS = 0.001

# Each comparison buys one BTC leg and sells the other. Both legs incur fees,
# including when they share a venue. The data do not measure spread or slippage.
ROUND_TRIP_USDT_USD = FEE_BINANCEUS + FEE_COINBASE
ROUND_TRIP_USDC_USD = FEE_BITSTAMP + FEE_COINBASE
ROUND_TRIP_USDT_USDC = 2 * FEE_BINANCEUS
ROUND_TRIP_USDC_USD_BITSTAMP = 2 * FEE_BITSTAMP
