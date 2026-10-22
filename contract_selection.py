from dataclasses import dataclass
from datetime import date, timedelta


# Te wartości są celowo zebrane w jednym miejscu. Po uzgodnieniu zakresu
# kontraktów wystarczy zmienić przesunięcia, bez przebudowy reszty aplikacji.
WEEK_OFFSETS = (2, 3, 4)
MONTH_OFFSETS = (1, 2, 3, 4)
QUARTER_OFFSETS = (1, 2)
YEAR_OFFSETS = (1,)


@dataclass(frozen=True)
class ContractSet:
    weeks: tuple[str, ...]
    months: tuple[str, ...]
    quarters: tuple[str, ...]
    years: tuple[str, ...]


def _iso_week_after(session_date: date, offset: int) -> tuple[int, int]:
    target = session_date + timedelta(weeks=offset)
    iso_year, iso_week, _ = target.isocalendar()
    return iso_week, iso_year % 100


def _month_after(session_date: date, offset: int) -> tuple[int, int]:
    absolute_month = session_date.year * 12 + session_date.month - 1 + offset
    year, zero_based_month = divmod(absolute_month, 12)
    return zero_based_month + 1, year % 100


def _quarter_after(session_date: date, offset: int) -> tuple[int, int]:
    current_quarter = (session_date.month - 1) // 3
    absolute_quarter = session_date.year * 4 + current_quarter + offset
    year, zero_based_quarter = divmod(absolute_quarter, 4)
    return zero_based_quarter + 1, year % 100


def build_contract_set(session_date: date, *, gas: bool) -> ContractSet:
    prefix = "GAS_BASE" if gas else "BASE"
    weeks = tuple(
        f"{prefix}_W-{week:02d}-{year:02d}"
        for week, year in (
            _iso_week_after(session_date, offset) for offset in WEEK_OFFSETS
        )
    )
    months = tuple(
        f"{prefix}_M-{month:02d}-{year:02d}"
        for month, year in (
            _month_after(session_date, offset) for offset in MONTH_OFFSETS
        )
    )
    quarters = tuple(
        f"{prefix}_Q-{quarter}-{year:02d}"
        for quarter, year in (
            _quarter_after(session_date, offset) for offset in QUARTER_OFFSETS
        )
    )
    years = tuple(
        f"{prefix}_Y-{(session_date.year + offset) % 100:02d}"
        for offset in YEAR_OFFSETS
    )
    return ContractSet(weeks, months, quarters, years)
