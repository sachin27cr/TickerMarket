"""Company names for display: the name people actually use, never the bare NSE symbol.

1. A hand-made list of everyday names for well-known companies (TCS, L&T, SBI, HUL, IndiGo...).
2. Otherwise NSE's official company name (equity list), tidied: "Limited/Ltd", "(India)" and similar removed,
   and shortened at a word boundary if it is still long.
3. If NSE's list is unavailable, the symbol is used as a last resort.
"""
import re

COMMON = {
    'TCS': 'TCS', 'INFY': 'Infosys', 'HCLTECH': 'HCLTech', 'WIPRO': 'Wipro', 'TECHM': 'Tech Mahindra',
    'LTIM': 'LTIMindtree', 'PERSISTENT': 'Persistent', 'COFORGE': 'Coforge', 'MPHASIS': 'Mphasis', 'KPITTECH': 'KPIT Tech',
    'OFSS': 'Oracle Financial', 'TATAELXSI': 'Tata Elxsi', 'TATACOMM': 'Tata Communications',
    'HDFCBANK': 'HDFC Bank', 'ICICIBANK': 'ICICI Bank', 'SBIN': 'SBI', 'KOTAKBANK': 'Kotak Bank', 'AXISBANK': 'Axis Bank',
    'INDUSINDBK': 'IndusInd Bank', 'BANKBARODA': 'Bank of Baroda', 'PNB': 'PNB', 'CANBK': 'Canara Bank',
    'UNIONBANK': 'Union Bank', 'IDFCFIRSTB': 'IDFC First Bank', 'FEDERALBNK': 'Federal Bank', 'AUBANK': 'AU Bank',
    'BANDHANBNK': 'Bandhan Bank', 'YESBANK': 'Yes Bank', 'INDIANB': 'Indian Bank', 'BANKINDIA': 'Bank of India',
    'IOB': 'Indian Overseas Bank', 'CENTRALBK': 'Central Bank', 'UCOBANK': 'UCO Bank', 'MAHABANK': 'Bank of Maharashtra',
    'BAJFINANCE': 'Bajaj Finance', 'BAJAJFINSV': 'Bajaj Finserv', 'BAJAJHFL': 'Bajaj Housing Finance',
    'SHRIRAMFIN': 'Shriram Finance', 'CHOLAFIN': 'Chola Finance', 'MUTHOOTFIN': 'Muthoot Finance',
    'LICHSGFIN': 'LIC Housing Finance', 'SBICARD': 'SBI Card', 'JIOFIN': 'Jio Financial', 'PFC': 'PFC', 'RECLTD': 'REC',
    'IRFC': 'IRFC', 'LICI': 'LIC', 'SBILIFE': 'SBI Life', 'HDFCLIFE': 'HDFC Life', 'ICICIPRULI': 'ICICI Pru Life',
    'ICICIGI': 'ICICI Lombard', 'STARHEALTH': 'Star Health', 'HDFCAMC': 'HDFC AMC', 'NAM-INDIA': 'Nippon AMC',
    'CDSL': 'CDSL', 'BSE': 'BSE', 'MCX': 'MCX', 'ANGELONE': 'Angel One', 'POLICYBZR': 'Policybazaar', 'PAYTM': 'Paytm',
    'RELIANCE': 'Reliance', 'ONGC': 'ONGC', 'IOC': 'Indian Oil', 'BPCL': 'BPCL', 'HINDPETRO': 'HPCL', 'GAIL': 'GAIL',
    'OIL': 'Oil India', 'PETRONET': 'Petronet LNG', 'COALINDIA': 'Coal India', 'NTPC': 'NTPC', 'POWERGRID': 'Power Grid',
    'TATAPOWER': 'Tata Power', 'ADANIPOWER': 'Adani Power', 'ADANIGREEN': 'Adani Green', 'ADANIENSOL': 'Adani Energy',
    'JSWENERGY': 'JSW Energy', 'NHPC': 'NHPC', 'SUZLON': 'Suzlon', 'INOXWIND': 'Inox Wind', 'WAAREEENER': 'Waaree Energies',
    'PREMIERENE': 'Premier Energies', 'NTPCGREEN': 'NTPC Green',
    'LT': 'L&T', 'ADANIENT': 'Adani Enterprises', 'ADANIPORTS': 'Adani Ports', 'BEL': 'BEL', 'HAL': 'HAL', 'BHEL': 'BHEL',
    'MAZDOCK': 'Mazagon Dock', 'COCHINSHIP': 'Cochin Shipyard', 'BDL': 'Bharat Dynamics', 'BEML': 'BEML',
    'SOLARINDS': 'Solar Industries', 'DATAPATTNS': 'Data Patterns', 'SIEMENS': 'Siemens', 'ABB': 'ABB India',
    'CUMMINSIND': 'Cummins India', 'BHARATFORG': 'Bharat Forge', 'POLYCAB': 'Polycab', 'HAVELLS': 'Havells',
    'DIXON': 'Dixon', 'CGPOWER': 'CG Power', 'IRCTC': 'IRCTC', 'RVNL': 'RVNL', 'IRCON': 'IRCON',
    'MARUTI': 'Maruti Suzuki', 'M&M': 'M&M', 'TATAMOTORS': 'Tata Motors', 'BAJAJ-AUTO': 'Bajaj Auto',
    'HEROMOTOCO': 'Hero MotoCorp', 'EICHERMOT': 'Eicher Motors', 'TVSMOTOR': 'TVS Motor', 'ASHOKLEY': 'Ashok Leyland',
    'MOTHERSON': 'Motherson', 'BOSCHLTD': 'Bosch', 'MRF': 'MRF', 'TIINDIA': 'Tube Investments', 'HYUNDAI': 'Hyundai India',
    'TATASTEEL': 'Tata Steel', 'JSWSTEEL': 'JSW Steel', 'HINDALCO': 'Hindalco', 'VEDL': 'Vedanta', 'HINDZINC': 'Hindustan Zinc',
    'SAIL': 'SAIL', 'NMDC': 'NMDC', 'JINDALSTEL': 'Jindal Steel', 'NATIONALUM': 'NALCO',
    'ULTRACEMCO': 'UltraTech Cement', 'GRASIM': 'Grasim', 'SHREECEM': 'Shree Cement', 'AMBUJACEM': 'Ambuja Cements',
    'ACC': 'ACC',
    'HINDUNILVR': 'HUL', 'ITC': 'ITC', 'NESTLEIND': 'Nestle India', 'BRITANNIA': 'Britannia', 'TATACONSUM': 'Tata Consumer',
    'DABUR': 'Dabur', 'MARICO': 'Marico', 'GODREJCP': 'Godrej Consumer', 'COLPAL': 'Colgate', 'UNITDSPR': 'United Spirits',
    'VBL': 'Varun Beverages', 'JUBLFOOD': 'Jubilant FoodWorks', 'ASIANPAINT': 'Asian Paints', 'BERGEPAINT': 'Berger Paints',
    'PIDILITIND': 'Pidilite', 'TITAN': 'Titan', 'KALYANKJIL': 'Kalyan Jewellers', 'TRENT': 'Trent', 'DMART': 'DMart',
    'PAGEIND': 'Page Industries', 'VOLTAS': 'Voltas', 'BLUESTARCO': 'Blue Star', 'CROMPTON': 'Crompton',
    'ETERNAL': 'Eternal (Zomato)', 'ZOMATO': 'Zomato', 'SWIGGY': 'Swiggy', 'NYKAA': 'Nykaa', 'NAUKRI': 'Info Edge (Naukri)',
    'INDIGO': 'IndiGo', 'INDHOTEL': 'Indian Hotels (Taj)', 'BHARTIARTL': 'Airtel', 'INDUSTOWER': 'Indus Towers',
    'IDEA': 'Vodafone Idea',
    'SUNPHARMA': 'Sun Pharma', 'DRREDDY': "Dr Reddy's", 'CIPLA': 'Cipla', 'DIVISLAB': "Divi's Labs", 'LUPIN': 'Lupin',
    'AUROPHARMA': 'Aurobindo Pharma', 'TORNTPHARM': 'Torrent Pharma', 'ZYDUSLIFE': 'Zydus', 'MANKIND': 'Mankind Pharma',
    'APOLLOHOSP': 'Apollo Hospitals', 'MAXHEALTH': 'Max Healthcare', 'FORTIS': 'Fortis',
    'DLF': 'DLF', 'LODHA': 'Lodha', 'GODREJPROP': 'Godrej Properties', 'OBEROIRLTY': 'Oberoi Realty',
    'PRESTIGE': 'Prestige', 'PHOENIXLTD': 'Phoenix Mills',
}
_DROP = re.compile(r'\s*\((?:india|i)\)|\b(limited|ltd\.?|ltd|pvt\.?|private|co\.?)\s*$', re.I)
MAX = 30
USED = set()                 # names shown this run (their digits are allowed in captions)
_master = None


def _official():
    global _master
    if _master is None:
        try:
            from . import market
            _master = dict(market.equity_master())
        except Exception:                          # noqa: BLE001 - names are cosmetic; never block a post
            _master = {}
    return _master


def tidy(name):
    n = re.sub(r'\s+', ' ', name).strip()
    for _ in range(3):
        n2 = _DROP.sub('', n).strip(' .,-')
        if n2 == n:
            break
        n = n2
    n = re.sub(r'^the\s+', '', n, flags=re.I)
    n = re.sub(r'\b([A-Z]{2,})\b', lambda m: m.group(1) if len(m.group(1)) <= 4 else m.group(1).title(), n)
    return n


def short(symbol, official=None):
    """Display name for an NSE symbol."""
    sym = (symbol or '').strip().upper()
    if sym in COMMON:
        n = COMMON[sym]
    else:
        off = official or _official().get(sym)
        n = tidy(off) if off else sym
        if len(n) > MAX:                           # very long names: the symbol is usually the common short form
            n = sym
    USED.add(n)
    return n


def name_numbers():
    """Digits inside names shown this run (e.g. '3M India', '360 ONE') so the number check accepts them."""
    return [float(x) for n in USED for x in re.findall(r'\d+(?:\.\d+)?', n)]
