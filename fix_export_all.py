import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILE_PATH = r"d:\IACC HCM\iPOS ACC\ACC PMKT\LedgerReport\index.html"
with open(FILE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Replace URLSearchParams in loadData, loadPurchaseData, loadWarehouseData
html = html.replace(
    "page: targetPage, page_size: targetPageSize",
    "page: targetPage, page_size: targetPageSize, export_all: 1"
)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print("Added export_all: 1 to URLSearchParams!")
