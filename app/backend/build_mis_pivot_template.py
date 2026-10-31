"""
One-time: turn the team's own MIS pivot workbook (e.g. "DR ICICI X-BKT NOV'26.xlsx") into the
RecoverIQ MIS-pivot TEMPLATE (app/assets/mis_pivot_template.xlsx + .json).

Keeps exactly what the team uses — the 10 real pivot tables, the 6 slicers (CYC, CALLER, AREA,
FOS NAME, DATE, V DATE), page filters and layout — and:
  * removes the scratch sheets (RE, Sheet2, file), the external link and calcChain
  * removes ALL customer data (MAIN rows, pivot cache records, cached pivot cells, target rows)
  * adds the RecoverIQ look: custom 'RecoverIQ Pivot' style, ₹ / % number formats, blue slicers,
    and cell styles used for the MAIN sheet + FOS target tables (ids saved in the .json)

USAGE (from app/backend):  python build_mis_pivot_template.py "path\\to\\team MIS.xlsx"
"""
import json
import re
import sys
import zipfile
from pathlib import Path

SRC = sys.argv[1]
OUT = Path(__file__).parent / "app" / "assets" / "mis_pivot_template.xlsx"
OUT_JSON = OUT.with_suffix(".json")

z = zipfile.ZipFile(SRC)
parts = {n: z.read(n) for n in z.namelist()}
order = z.namelist()
T = lambda n: parts[n].decode("utf-8")


def put(n, s):
    parts[n] = s.encode("utf-8")


def drop(n):
    parts.pop(n, None)
    if n in order:
        order.remove(n)


# ── 1. remove scratch sheets / external link / calcChain ─────────────────────────────
wb = T("xl/workbook.xml")
rels = T("xl/_rels/workbook.xml.rels")
ct = T("[Content_Types].xml")
sheets = re.findall(r'<sheet name="([^"]+)" sheetId="\d+" r:id="(rId\d+)"/>', wb)
rid_target = dict(re.findall(r'Id="(rId\d+)" Type="[^"]+" Target="([^"]+)"', rels))
keep = {"MIS", "MAIN"}
for name, rid in sheets:
    if name in keep:
        continue
    target = "xl/" + rid_target[rid]
    wb = re.sub(rf'<sheet name="{re.escape(name)}" sheetId="\d+" r:id="{rid}"/>', "", wb)
    rels = re.sub(rf'<Relationship Id="{rid}" [^>]*/>', "", rels)
    ct = ct.replace(f'<Override PartName="/{target}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>', "")
    drop(target)
    drop(target.replace("worksheets/", "worksheets/_rels/") + ".rels")
# external link
for rid, tgt in list(rid_target.items()):
    if "externalLink" in tgt or "calcChain" in tgt:
        rels = re.sub(rf'<Relationship Id="{rid}" [^>]*/>', "", rels)
        p = "xl/" + tgt
        ct = re.sub(rf'<Override PartName="/{re.escape(p)}"[^>]*/>', "", ct)
        drop(p)
        drop(p.replace("externalLinks/", "externalLinks/_rels/") + ".rels")
wb = re.sub(r"<externalReferences>.*?</externalReferences>", "", wb, flags=re.S)
wb = re.sub(r'<definedName name="_xlnm._FilterDatabase"[^>]*>[^<]*</definedName>', "", wb)
wb = wb.replace('refMode="R1C1" ', "")
# sheet order is MIS (localSheetId 0), MAIN (1)
put("xl/workbook.xml", wb); put("xl/_rels/workbook.xml.rels", rels); put("[Content_Types].xml", ct)
for n in list(parts):
    if n.startswith("xl/printerSettings/"):
        pass   # still referenced by MIS/MAIN rels — keep

# ── 2. styles ─────────────────────────────────────────────────────────────────────────
NAVY, BLUE, TOT, SUB, ZEB = "FF0F2747", "FF1D4ED8", "FFDCE6FA", "FFEEF3FF", "FFF7F9FC"
GREEN, RED, AMBER, VIOLET, SLATE, SKY, YEL = "FF15803D", "FFB91C1C", "FFB45309", "FF7C3AED", "FF64748B", "FF0369A1", "FFFFF7D6"
GREEN_L, RED_L, GRID = "FFDCFCE7", "FFFEE2E2", "FFD6DEEA"
st = T("xl/styles.xml")
NF_RUP, NF_PCT = 200, 201
assert "<numFmts" not in st
st = re.sub(r"(<styleSheet[^>]*>)", r'\1<numFmts count="2"><numFmt numFmtId="200" formatCode="&quot;₹&quot;#,##0"/>'
            r'<numFmt numFmtId="201" formatCode="0.0%"/></numFmts>', st, count=1)


def add_items(xml, tag, items):
    m = re.search(rf'<{tag} count="(\d+)"([^>]*)>', xml)
    n = int(m.group(1))
    xml = xml[:m.start()] + f'<{tag} count="{n + len(items)}"{m.group(2)}>' + xml[m.end():]
    end = xml.index(f"</{tag}>", m.start())
    return xml[:end] + "".join(items) + xml[end:], n


font = lambda col, b=True, sz=10: (f'<font>{"<b/>" if b else ""}<sz val="{sz}"/><color rgb="{col}"/>'
                                   f'<name val="Calibri"/><family val="2"/></font>')
st, F0 = add_items(st, "fonts", [font("FFFFFFFF"), font("FF0F2747"), font("FF92400E"), font("FF1F2937", False),
                                 font("FFFFFFFF", True, 11), font("FF166534"), font("FF991B1B")])
F_WHITE, F_NAVY, F_AMBER, F_TEXT, F_TITLE, F_GREEN, F_RED = range(F0, F0 + 7)
fills = [NAVY, BLUE, TOT, YEL, GREEN, RED, AMBER, VIOLET, SLATE, SKY, SUB, ZEB, GREEN_L, RED_L]
st, P0 = add_items(st, "fills", [f'<fill><patternFill patternType="solid"><fgColor rgb="{c}"/><bgColor indexed="64"/></patternFill></fill>' for c in fills])
FI = {c: P0 + i for i, c in enumerate(fills)}
thin = (f'<border><left style="thin"><color rgb="{GRID}"/></left><right style="thin"><color rgb="{GRID}"/></right>'
        f'<top style="thin"><color rgb="{GRID}"/></top><bottom style="thin"><color rgb="{GRID}"/></bottom><diagonal/></border>')
st, B_THIN = add_items(st, "borders", [thin])


def xf(numfmt=0, fnt=F_TEXT, fill=0, h="center", wrap=False):
    wr = ' wrapText="1"' if wrap else ""
    return (f'<xf numFmtId="{numfmt}" fontId="{fnt}" fillId="{fill}" borderId="{B_THIN}" xfId="0" applyNumberFormat="1" '
            f'applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="{h}" vertical="center"{wr}/></xf>')


defs = {
    # headers
    "h_navy": xf(0, F_WHITE, FI[NAVY], wrap=True), "h_blue": xf(0, F_WHITE, FI[BLUE], wrap=True),
    "h_green": xf(0, F_WHITE, FI[GREEN], wrap=True), "h_red": xf(0, F_WHITE, FI[RED], wrap=True),
    "h_amber": xf(0, F_WHITE, FI[AMBER], wrap=True), "h_slate": xf(0, F_WHITE, FI[SLATE], wrap=True),
    "h_sky": xf(0, F_WHITE, FI[SKY], wrap=True), "title": xf(0, F_TITLE, FI[VIOLET], "left"),
    "sel": xf(0, F_AMBER, FI[YEL]),
    # target-table body + totals
    "name": xf(0, F_TEXT, 0, "left"), "int": xf(3), "rup": xf(NF_RUP), "pct": xf(NF_PCT), "tgt": xf(9, F_AMBER, FI[YEL]),
    "t_name": xf(0, F_NAVY, FI[TOT], "left"), "t_int": xf(3, F_NAVY, FI[TOT]), "t_rup": xf(NF_RUP, F_NAVY, FI[TOT]),
    "t_pct": xf(NF_PCT, F_NAVY, FI[TOT]), "t_tgt": xf(9, F_NAVY, FI[TOT]),
    # MAIN sheet body (plain + zebra) and paid/unpaid pills
    "m_txt": xf(0, F_TEXT, 0, "left"), "m_txt_z": xf(0, F_TEXT, FI[ZEB], "left"),
    "m_num": xf(0), "m_num_z": xf(0, F_TEXT, FI[ZEB]),
    "m_rup": xf(NF_RUP), "m_rup_z": xf(NF_RUP, F_TEXT, FI[ZEB]),
    "m_paid": xf(0, F_GREEN, FI[GREEN_L]), "m_unpaid": xf(0, F_RED, FI[RED_L]),
}
st, X0 = add_items(st, "cellXfs", list(defs.values()))
XF = {k: X0 + i for i, k in enumerate(defs)}


def dxf(fill=None, fc=None, bold=False, top=None):
    f = f'<font>{"<b/>" if bold else ""}<color rgb="{fc}"/></font>' if (fc or bold) else ""
    fi = f'<fill><patternFill patternType="solid"><bgColor rgb="{fill}"/></patternFill></fill>' if fill else ""
    t = f'<top style="{top[0]}"><color rgb="{top[1]}"/></top>' if top else f'<top style="thin"><color rgb="{GRID}"/></top>'
    bd = (f'<border><left style="thin"><color rgb="{GRID}"/></left><right style="thin"><color rgb="{GRID}"/></right>{t}'
          f'<bottom style="thin"><color rgb="{GRID}"/></bottom><vertical style="thin"><color rgb="{GRID}"/></vertical>'
          f'<horizontal style="thin"><color rgb="{GRID}"/></horizontal></border>')
    return f"<dxf>{f}{fi}{bd}</dxf>"


elements = [
    ("wholeTable", dxf(fc="FF1F2937")), ("headerRow", dxf(NAVY, "FFFFFFFF", True)),
    ("firstHeaderCell", dxf(NAVY, "FFFFFFFF", True)), ("totalRow", dxf(TOT, NAVY, True, ("medium", NAVY))),
    ("lastColumn", dxf(SUB, NAVY, True)), ("firstColumn", dxf(None, NAVY, True)), ("firstRowStripe", dxf(ZEB)),
    ("firstColumnSubheading", dxf(BLUE, "FFFFFFFF", True)), ("secondColumnSubheading", dxf("FF3B82F6", "FFFFFFFF", True)),
    ("firstSubtotalColumn", dxf(SUB, NAVY, True)), ("firstRowSubheading", dxf(SUB, NAVY, True)),
    ("firstSubtotalRow", dxf(SUB, NAVY, True)), ("pageFieldLabels", dxf(SUB, NAVY, True)),
    ("pageFieldValues", dxf(YEL, "FF92400E", True)),
]
st, D0 = add_items(st, "dxfs", [e[1] for e in elements])
style_xml = ('<tableStyle name="RecoverIQ Pivot" table="0" count="%d">' % len(elements)
             + "".join(f'<tableStyleElement type="{t}" dxfId="{D0 + i}"/>' for i, (t, _) in enumerate(elements)) + "</tableStyle>")
st = re.sub(r'<tableStyles count="0"([^>]*)/>', r'<tableStyles count="1"\1>' + style_xml + "</tableStyles>", st)
assert "RecoverIQ Pivot" in st
put("xl/styles.xml", st)

# ── 3. pivots: style, number formats, no manual formats; cache refreshes on open ─────────
for n in [p for p in parts if re.match(r"xl/pivotTables/pivotTable\d+\.xml$", p)]:
    x = T(n)
    x = re.sub(r"<pivotTableStyleInfo [^>]*/>", '<pivotTableStyleInfo name="RecoverIQ Pivot" showRowHeaders="1" '
               'showColHeaders="1" showRowStripes="1" showColStripes="0" showLastColumn="1"/>', x)

    def nf(m):
        tag = re.sub(r' numFmtId="\d+"', "", m.group(0))
        name = (re.search(r' name="([^"]*)"', tag).group(1) or "").upper().strip()
        fid = NF_PCT if ('showDataAs="percent' in tag or name == "%") else 3 if ('subtotal="count"' in tag or name.startswith("COUNT")) else NF_RUP
        return tag.replace("<dataField ", f'<dataField numFmtId="{fid}" ', 1)
    x = re.sub(r"<dataField [^>]*?/?>", nf, x)
    x = x.replace('applyNumberFormats="0"', 'applyNumberFormats="1"')
    x = re.sub(r'<formats count="\d+">.*?</formats>', "", x, flags=re.S)
    put(n, x)
cd = T("xl/pivotCache/pivotCacheDefinition1.xml")
cd = re.sub(r' refreshedBy="[^"]*"', ' refreshedBy="RecoverIQ"', cd)
if "refreshOnLoad" not in cd:
    cd = cd.replace("<pivotCacheDefinition ", '<pivotCacheDefinition refreshOnLoad="1" ', 1)
put("xl/pivotCache/pivotCacheDefinition1.xml", cd)
for n in [p for p in parts if p.startswith("xl/slicers/") and p.endswith(".xml")]:
    put(n, re.sub(r"(<slicer )(?![^>]*style=)", r'\1style="SlicerStyleDark1" ', T(n)))

# MAIN table: cells carry their own RecoverIQ styling, so no banded table style on top
tb = T("xl/tables/table1.xml")
tb = re.sub(r"<tableStyleInfo [^>]*/>", '<tableStyleInfo showFirstColumn="0" showLastColumn="0" showRowStripes="0" showColumnStripes="0"/>', tb)
put("xl/tables/table1.xml", tb)

# ── 4. MIS sheet: grid lines off; FOS-target area cleared (regenerated per download) ─────
sh = T("xl/worksheets/sheet1.xml")
sh = re.sub(r"<sheetView ", '<sheetView showGridLines="0" ', sh, count=1) if "showGridLines" not in sh else sh
sh = re.sub(r'topLeftCell="[^"]*" ', "", sh, count=1)
put("xl/worksheets/sheet1.xml", sh)

meta = {"xf": XF, "nf_rup": NF_RUP, "nf_pct": NF_PCT, "source": Path(SRC).name}
OUT.parent.mkdir(parents=True, exist_ok=True)
# The generator (app/mis_pivot.py) wipes every data part (MAIN rows, cache records, pivot cells,
# target tables) on each build; run it once here with NO rows so the stored template holds no data.
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zo:
    for n in order:
        if n in parts:
            zo.writestr(n, parts[n])
OUT_JSON.write_text(json.dumps(meta, indent=1), encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from app import mis_pivot  # noqa: E402
OUT.write_bytes(mis_pivot.render_xlsx([], "MIS", {}, template=OUT.read_bytes()))
print("template saved:", OUT)
