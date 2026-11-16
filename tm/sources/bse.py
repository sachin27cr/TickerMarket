"""BSE index levels (official source for the Sensex) via the bsedata package, which reads
the same JSON as bseindia.com. Raises nse.SourceError on any problem."""
from .nse import SourceError


def _num(v):
    return float(str(v).replace(',', '').strip())


def sensex():
    try:
        from bsedata.bse import BSE
        data = BSE(update_codes=False).getIndices(category='market_cap/broad')
    except Exception as e:                           # noqa: BLE001
        raise SourceError(f'BSE indices: {e}')
    for row in data.get('indices', []):
        name = str(row.get('name', '')).upper().replace('S&P', '').strip()
        if name in ('BSE SENSEX', 'SENSEX'):
            try:
                close, chg = _num(row['currentValue']), _num(row['change'])
                return {'last': close, 'chg': chg, 'pct': _num(row['pChange']), 'prev': close - chg}
            except (KeyError, ValueError) as e:
                raise SourceError(f'BSE Sensex row unreadable: {e}')
    raise SourceError('Sensex not found in BSE indices')
