import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILE_PATH = r"d:\IACC HCM\iPOS ACC\ACC PMKT\LedgerReport\index.html"
with open(FILE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# 1. Fix buildGroupedData float parsing
buildGroupedData_find = """                    if(sumFields) {
                        if(row.DEBIT_CREDIT === 'DEB') node.sums.DEBIT = (node.sums.DEBIT || 0) + (row.AMOUNT || 0);
                        if(row.DEBIT_CREDIT === 'CRD') node.sums.CREDIT = (node.sums.CREDIT || 0) + (row.AMOUNT || 0);
                        if(row.TOTAL_AMOUNT) node.sums.TOTAL_AMOUNT = (node.sums.TOTAL_AMOUNT || 0) + (row.TOTAL_AMOUNT || 0);
                        if(row.AMOUNT && row.DEBIT_CREDIT !== 'DEB' && row.DEBIT_CREDIT !== 'CRD') node.sums.AMOUNT = (node.sums.AMOUNT || 0) + (row.AMOUNT || 0);
                    }"""

buildGroupedData_replace = """                    if(sumFields) {
                        if(row.DEBIT_CREDIT === 'DEB') node.sums.DEBIT = (node.sums.DEBIT || 0) + (parseFloat(row.AMOUNT) || 0);
                        if(row.DEBIT_CREDIT === 'CRD') node.sums.CREDIT = (node.sums.CREDIT || 0) + (parseFloat(row.AMOUNT) || 0);
                        if(row.TOTAL_AMOUNT) node.sums.TOTAL_AMOUNT = (node.sums.TOTAL_AMOUNT || 0) + (parseFloat(row.TOTAL_AMOUNT) || 0);
                        if(row.AMOUNT && row.DEBIT_CREDIT !== 'DEB' && row.DEBIT_CREDIT !== 'CRD') node.sums.AMOUNT = (node.sums.AMOUNT || 0) + (parseFloat(row.AMOUNT) || 0);
                    }"""

html = html.replace(buildGroupedData_find, buildGroupedData_replace)

# 2. Fix LedgerGroupRow colSpan and maximumFractionDigits
ledger_find = """<td colSpan={10} className="px-4 py-1.5 border-r border-indigo-200/30 whitespace-nowrap">"""
ledger_replace = """<td colSpan={8} className="px-4 py-1.5 border-r border-indigo-200/30 whitespace-nowrap">"""
html = html.replace(ledger_find, ledger_replace)

html = html.replace(
    "node.sums.DEBIT.toLocaleString('en-US', {minimumFractionDigits:2})",
    "node.sums.DEBIT.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})"
)
html = html.replace(
    "node.sums.CREDIT.toLocaleString('en-US', {minimumFractionDigits:2})",
    "node.sums.CREDIT.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})"
)
html = html.replace(
    "node.sums.TOTAL_AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0})",
    "node.sums.TOTAL_AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0})"
)
html = html.replace(
    "node.sums.AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0})",
    "node.sums.AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0})"
)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print("Fixed colSpan and float parsing!")
