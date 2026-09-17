import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILE_PATH = r"d:\IACC HCM\iPOS ACC\ACC PMKT\LedgerReport\index.html"
with open(FILE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Fix Ledger
html = html.replace(
    "{ledgerVS.topPadding > 0 && <tr style={{ height: ledgerVS.topPadding }}><td colSpan=\"100\"></td></tr>}",
    "{ledgerVS.topPadding > 0 && <tr style={{ height: ledgerVS.topPadding }}><td colSpan=\"100\" style={{ height: ledgerVS.topPadding, padding: 0, border: 0 }}></td></tr>}"
)
html = html.replace(
    "{ledgerVS.bottomPadding > 0 && <tr style={{ height: ledgerVS.bottomPadding }}><td colSpan=\"100\"></td></tr>}",
    "{ledgerVS.bottomPadding > 0 && <tr style={{ height: ledgerVS.bottomPadding }}><td colSpan=\"100\" style={{ height: ledgerVS.bottomPadding, padding: 0, border: 0 }}></td></tr>}"
)

# Fix Purchase
html = html.replace(
    "{purchaseVS.topPadding > 0 && <tr style={{ height: purchaseVS.topPadding }}><td colSpan=\"100\"></td></tr>}",
    "{purchaseVS.topPadding > 0 && <tr style={{ height: purchaseVS.topPadding }}><td colSpan=\"100\" style={{ height: purchaseVS.topPadding, padding: 0, border: 0 }}></td></tr>}"
)
html = html.replace(
    "{purchaseVS.bottomPadding > 0 && <tr style={{ height: purchaseVS.bottomPadding }}><td colSpan=\"100\"></td></tr>}",
    "{purchaseVS.bottomPadding > 0 && <tr style={{ height: purchaseVS.bottomPadding }}><td colSpan=\"100\" style={{ height: purchaseVS.bottomPadding, padding: 0, border: 0 }}></td></tr>}"
)

# Fix Warehouse
html = html.replace(
    "{warehouseVS.topPadding > 0 && <tr style={{ height: warehouseVS.topPadding }}><td colSpan=\"100\"></td></tr>}",
    "{warehouseVS.topPadding > 0 && <tr style={{ height: warehouseVS.topPadding }}><td colSpan=\"100\" style={{ height: warehouseVS.topPadding, padding: 0, border: 0 }}></td></tr>}"
)
html = html.replace(
    "{warehouseVS.bottomPadding > 0 && <tr style={{ height: warehouseVS.bottomPadding }}><td colSpan=\"100\"></td></tr>}",
    "{warehouseVS.bottomPadding > 0 && <tr style={{ height: warehouseVS.bottomPadding }}><td colSpan=\"100\" style={{ height: warehouseVS.bottomPadding, padding: 0, border: 0 }}></td></tr>}"
)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print("Fixed Virtual Scroll padding TRs!")
