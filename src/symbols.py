"""Maps Refinitiv/LSEG source symbols to identifiers used by each data source.

For US filers (us_filer=True):
  - ``cik`` is the EDGAR CIK (zero-padded to 10 digits).
  - Route: EDGAR submissions API → filing text.

For non-US (us_filer=False):
  - ``cik`` is None.
  - Route: local files under filings/{filings_dir}/.

CIKs annotated with ``# VERIFY`` should be confirmed at:
  https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=NAME&type=&owner=include&count=10
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class SymbolInfo:
    src_symbol: str       # Refinitiv/LSEG symbol (primary key in SYMBOL_TABLE)
    name: str             # Human-readable company name
    ticker: str           # Clean ticker for news queries and filings/ folder naming
    us_filer: bool        # True → EDGAR; False → local filings/{filings_dir}/
    cik: Optional[str]    # EDGAR CIK zero-padded to 10 digits; None for non-US
    filings_dir: str      # Sub-folder name under filings/ for local documents


# ---------------------------------------------------------------------------
# Complete mapping: Refinitiv src_symbol → SymbolInfo
# CIKs confirmed where known; others marked VERIFY.
# ---------------------------------------------------------------------------
SYMBOL_TABLE: Dict[str, SymbolInfo] = {
    "ADBE.O":    SymbolInfo("ADBE.O",    "Adobe",                   "ADBE",  True,  "0000796343", "ADBE"),
    "HY9Hy.F":   SymbolInfo("HY9Hy.F",   "SK Hynix",                "000660",False, None,         "SK_HYNIX"),
    "MAI.V":     SymbolInfo("MAI.V",     "Minera Alamos",            "MAI",   False, None,         "MAI"),
    "PAAS.TO":   SymbolInfo("PAAS.TO",   "Pan American Silver",      "PAAS",  True,  "0001006249", "PAAS"),    # 40-F VERIFY
    "WPM":       SymbolInfo("WPM",       "Wheaton Precious Metals",  "WPM",   True,  "0001285785", "WPM"),     # 40-F VERIFY
    "MTO.L":     SymbolInfo("MTO.L",     "Mitie",                    "MTO",   False, None,         "MITIE"),
    "VBNK.O":    SymbolInfo("VBNK.O",    "VersaBank",                "VBNK",  True,  "0001642545", "VBNK"),    # 40-F VERIFY
    "APM.TO":    SymbolInfo("APM.TO",    "Andean Precious Metals",   "APM",   False, None,         "APM"),
    "CSL":       SymbolInfo("CSL",       "Carlisle",                 "CSL",   True,  "0000016160", "CSL"),
    "GOOG.O":    SymbolInfo("GOOG.O",    "Alphabet C",               "GOOG",  True,  "0001652044", "GOOG"),
    "NA9n.DE":   SymbolInfo("NA9n.DE",   "Nagarro SE",               "NA9",   False, None,         "NAGARRO"),
    "VLE.TO":    SymbolInfo("VLE.TO",    "Valeura Energy",           "VLE",   False, None,         "VALEURA"),
    "WAF.AX":    SymbolInfo("WAF.AX",    "West African Resources",   "WAF",   False, None,         "WAF"),
    "TTAM.K":    SymbolInfo("TTAM.K",    "Titan America",            "TTAM",  True,  "0002036535", "TTAM"),    # VERIFY
    "SAN":       SymbolInfo("SAN",       "Santander",                "SAN",   True,  "0000089676", "SAN"),     # 20-F VERIFY
    "BN":        SymbolInfo("BN",        "Brookfield",               "BN",    True,  "0001001085", "BN"),      # 40-F VERIFY
    "GSY.TO":    SymbolInfo("GSY.TO",    "goeasy",                   "GSY",   False, None,         "GOEASY"),
    "SOIL.TO":   SymbolInfo("SOIL.TO",   "Saturn Oil",               "SOIL",  False, None,         "SATURN_OIL"),
    "NVDA.O":    SymbolInfo("NVDA.O",    "NVIDIA",                   "NVDA",  True,  "0001045810", "NVDA"),
    "TITC.BR":   SymbolInfo("TITC.BR",   "Titan Cement",             "TITC",  False, None,         "TITAN_CEMENT"),
    "WOSG.L":    SymbolInfo("WOSG.L",    "Watches of Switzerland",   "WOSG",  False, None,         "WOSG"),
    "BLOP.WA":   SymbolInfo("BLOP.WA",   "Bloober",                  "BLOP",  False, None,         "BLOOBER"),
    "MAA":       SymbolInfo("MAA",       "Mid-America Apartment",    "MAA",   True,  "0000912093", "MAA"),
    "OPT.L":     SymbolInfo("OPT.L",     "Optima Health",            "OPT",   False, None,         "OPTIMA_HEALTH"),
    "TEPRF.PA":  SymbolInfo("TEPRF.PA",  "Teleperformance",          "TEP",   False, None,         "TELEPERFORMANCE"),
    "ARE":       SymbolInfo("ARE",       "Alexandria RE",            "ARE",   True,  "0000906709", "ARE"),
    "VRLA.PA":   SymbolInfo("VRLA.PA",   "Verallia",                 "VRLA",  False, None,         "VERALLIA"),
    "MAD.AX":    SymbolInfo("MAD.AX",    "Mader Group",              "MAD",   False, None,         "MADER"),
    "BYG.L":     SymbolInfo("BYG.L",     "Big Yellow",               "BYG",   False, None,         "BIG_YELLOW"),
    "EVOG.ST":   SymbolInfo("EVOG.ST",   "Evolution AB",             "EVO",   False, None,         "EVOLUTION"),
    "CGEO.L":    SymbolInfo("CGEO.L",    "Georgia Capital",          "CGEO",  False, None,         "GEORGIA_CAPITAL"),
    "LDA.MC":    SymbolInfo("LDA.MC",    "Linea Directa",            "LDA",   False, None,         "LINEA_DIRECTA"),
    "NWLF.MI":   SymbolInfo("NWLF.MI",   "Newprinces",               "NWLF",  False, None,         "NEWPRINCES"),
    "CLAR.O":    SymbolInfo("CLAR.O",    "Clarus",                   "CLAR",  True,  "0000788920", "CLAR"),
    "EUFI.PA":   SymbolInfo("EUFI.PA",   "Eurofins Scientific",      "ERF",   False, None,         "EUROFINS"),
    "CNXC.O":    SymbolInfo("CNXC.O",    "Concentrix",               "CNXC",  True,  "0001803599", "CNXC"),
    "BAM":       SymbolInfo("BAM",       "Brookfield Asset Mgmt",    "BAM",   True,  "0001900010", "BAM"),     # 40-F VERIFY
    "KPG.AX":    SymbolInfo("KPG.AX",    "Kelly Partners",           "KPG",   False, None,         "KELLY_PARTNERS"),
    "DAVA.K":    SymbolInfo("DAVA.K",    "Endava",                   "DAVA",  True,  "0001752474", "DAVA"),    # 20-F VERIFY
    "CIGI.O":    SymbolInfo("CIGI.O",    "Colliers International",   "CIGI",  True,  "0001628928", "CIGI"),    # 40-F VERIFY
    "CPRT.O":    SymbolInfo("CPRT.O",    "Copart",                   "CPRT",  True,  "0000723254", "CPRT"),
    "MBR.WA":    SymbolInfo("MBR.WA",    "Mo-Bruk SA",               "MBR",   False, None,         "MOBRUK"),
    "POOL.O":    SymbolInfo("POOL.O",    "Pool",                     "POOL",  True,  "0000945841", "POOL"),
    "SDIS.L":    SymbolInfo("SDIS.L",    "SDI Group",                "SDI",   False, None,         "SDI_GROUP"),
    "TRU":       SymbolInfo("TRU",       "TransUnion",               "TRU",   True,  "0001552033", "TRU"),
    "MSFT.O":    SymbolInfo("MSFT.O",    "Microsoft",                "MSFT",  True,  "0000789019", "MSFT"),
    "META.O":    SymbolInfo("META.O",    "Meta Platforms",           "META",  True,  "0001326801", "META"),
    "MACF.L":    SymbolInfo("MACF.L",    "Macfarlane Group",         "MACF",  False, None,         "MACFARLANE"),
    "STORb.ST":  SymbolInfo("STORb.ST",  "Storskogen AB",            "STOR",  False, None,         "STORSKOGEN"),
    "APR.WA":    SymbolInfo("APR.WA",    "Auto Partner",             "APR",   False, None,         "AUTO_PARTNER"),
}


def get_symbol_info(src_symbol: str) -> Optional[SymbolInfo]:
    """Return SymbolInfo for the given Refinitiv/LSEG src_symbol, or None."""
    return SYMBOL_TABLE.get(src_symbol)
