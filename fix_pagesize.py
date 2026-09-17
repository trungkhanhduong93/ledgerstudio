import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILE_PATH = r"d:\IACC HCM\iPOS ACC\ACC PMKT\LedgerReport\index.html"
with open(FILE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Replace page_size: 100 with page_size: 9999999 to load all rows for Virtual Scroll
pattern = r"page_size:\s*100\s*\}"
html = re.sub(pattern, "page_size: 9999999 }", html)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print("Updated page_size to 9999999 for full data load!")
