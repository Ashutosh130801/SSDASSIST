"""Bank → product catalog for the collections agency.

Each case-upload is for one bank + one product + a segment (Credit Card or PL/BL).
Keep this in sync with the agency's live product sheet.
"""

BANK_PRODUCTS = {
    "ICICI": ["DR", "FR", "FCPU", "2 BKT", "4 BKT", "SFFRC", "180+", "3 BKT"],
    "AXIS": ["X BKT", "BL X BKT", "PL X BKT", "PL NPA", "180+", "2 BKT", "3 BKT", "CC NPA"],
    "RBL": ["BRBL BKT 3"],
    "PIRAMAL": ["2 BKT"],
    "NAVI": ["X-5 BKT", "180+"],
    "CHOLA": ["CD 2,3,4"],
    "HERO FIN CORP": ["NPA", "180+"],
    "HOMECREDIT": ["180+"],
    "TVS CREDIT": ["180+"],
}

# The loan segment chosen at upload time.
SEGMENTS = ["Credit Card", "PL/BL"]


def catalog() -> dict:
    return {"banks": list(BANK_PRODUCTS.keys()), "products": BANK_PRODUCTS, "segments": SEGMENTS}
