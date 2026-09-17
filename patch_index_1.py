import os

file_path = r"D:\IACC HCM\iPOS ACC\ACC PMKT\LedgerStudio\index.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update loadReportData to include page and page_size
old_query = "const query = new URLSearchParams({ from_date: filters.from_date, to_date: filters.to_date, org_ids: filters.org_ids.join(','), job_ids: filters.job_ids.join(',') });"
new_query = "const query = new URLSearchParams({ from_date: filters.from_date, to_date: filters.to_date, org_ids: filters.org_ids.join(','), job_ids: filters.job_ids.join(','), page: filters.page, page_size: filters.page_size });"
content = content.replace(old_query, new_query)

# 2. Add Export Excel Backend function inside ReportTab
export_func_str = """
            const exportToExcelBackend = () => {
                const query = new URLSearchParams({ 
                    report_type: reportType, 
                    from_date: filters.from_date, 
                    to_date: filters.to_date, 
                    org_ids: filters.org_ids.join(','), 
                    account_id: filters.acc_ids.join(',') 
                });
                window.location.href = `/api/export_excel_backend?${query.toString()}`;
            };
"""
export_hook = "const exportToExcel = () => {"
content = content.replace(export_hook, export_func_str + "\n            " + export_hook)

# 3. Replace the Export button in ReportTab
old_export_btn = '<button onClick={exportToExcel} disabled={loading} className="bg-indigo-600 text-white px-5 h-[32px] rounded-lg font-black text-[9px] shadow-lg hover:bg-indigo-700 transition-all uppercase tracking-widest flex items-center gap-2">'
new_export_btn = '<button onClick={reportType === "BC007" || reportType === "BC008" ? exportToExcelBackend : exportToExcel} disabled={loading} className="bg-emerald-600 text-white px-5 h-[32px] rounded-lg font-black text-[9px] shadow-lg hover:bg-emerald-700 transition-all uppercase tracking-widest flex items-center gap-2">'
content = content.replace(old_export_btn, new_export_btn)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Basic index.html replacements applied.")
