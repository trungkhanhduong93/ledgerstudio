import os

file_path = r"D:\IACC HCM\iPOS ACC\ACC PMKT\LedgerStudio\index.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. BC007 sums replacement
bc007_old = """
                                            <tr className="bg-slate-100 font-black">
                                                <td colSpan="6" className="border border-slate-300 px-3 py-2 text-right uppercase tracking-widest text-xs">Cộng lũy kế</td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum((reportData.data || []).filter(r => r.debit_credit === 'DEB').reduce((sum, r) => sum + r.amount, 0))}
                                                </td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum((reportData.data || []).filter(r => r.debit_credit === 'CRD').reduce((sum, r) => sum + r.amount, 0))}
                                                </td>
                                            </tr>
"""
bc007_new = """
                                            <tr className="bg-slate-100 font-black">
                                                <td colSpan="6" className="border border-slate-300 px-3 py-2 text-right uppercase tracking-widest text-xs">Cộng lũy kế</td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum(reportData.period_sums ? reportData.period_sums.deb : 0)}
                                                </td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum(reportData.period_sums ? reportData.period_sums.crd : 0)}
                                                </td>
                                            </tr>
"""
content = content.replace(bc007_old.strip(), bc007_new.strip())

# 2. BC008 sums replacement
bc008_running = """
                                            {(() => {
                                                let runningDeb = reportData.opening_balance ? reportData.opening_balance.deb : 0;
                                                let runningCrd = reportData.opening_balance ? reportData.opening_balance.crd : 0;
"""
bc008_running_new = """
                                            {(() => {
                                                let runningDeb = (reportData.opening_balance ? reportData.opening_balance.deb : 0) + (reportData.offset_balance ? reportData.offset_balance.deb : 0);
                                                let runningCrd = (reportData.opening_balance ? reportData.opening_balance.crd : 0) + (reportData.offset_balance ? reportData.offset_balance.crd : 0);
                                                const startNet = runningDeb - runningCrd;
                                                if (startNet > 0) { runningDeb = startNet; runningCrd = 0; }
                                                else if (startNet < 0) { runningCrd = Math.abs(startNet); runningDeb = 0; }
                                                else { runningDeb = 0; runningCrd = 0; }
"""
content = content.replace(bc008_running.strip(), bc008_running_new.strip())

bc008_sums = """
                                            <tr className="bg-slate-100 font-black">
                                                <td colSpan="5" className="border border-slate-300 px-3 py-2 text-right uppercase tracking-widest text-xs">Cộng phát sinh trong kỳ</td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum((reportData.data || []).filter(r => r.debit_credit === 'DEB').reduce((sum, r) => sum + r.amount, 0))}
                                                </td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum((reportData.data || []).filter(r => r.debit_credit === 'CRD').reduce((sum, r) => sum + r.amount, 0))}
                                                </td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                            </tr>
                                            {(() => {
                                                const totalSumDeb = (reportData.data || []).filter(r => r.debit_credit === 'DEB').reduce((sum, r) => sum + r.amount, 0);
                                                const totalSumCrd = (reportData.data || []).filter(r => r.debit_credit === 'CRD').reduce((sum, r) => sum + r.amount, 0);
"""
bc008_sums_new = """
                                            <tr className="bg-slate-100 font-black">
                                                <td colSpan="5" className="border border-slate-300 px-3 py-2 text-right uppercase tracking-widest text-xs">Cộng phát sinh trong kỳ</td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum(reportData.period_sums ? reportData.period_sums.deb : 0)}
                                                </td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum(reportData.period_sums ? reportData.period_sums.crd : 0)}
                                                </td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                            </tr>
                                            {(() => {
                                                const totalSumDeb = reportData.period_sums ? reportData.period_sums.deb : 0;
                                                const totalSumCrd = reportData.period_sums ? reportData.period_sums.crd : 0;
"""
content = content.replace(bc008_sums.strip(), bc008_sums_new.strip())


# 3. Add Pagination UI at the end of the table container
# We need to find the end of the table div for the report tab
end_table_div = """
                                    </table>
                                </div>
                            </div>
"""
pagination_ui = """
                                    </table>
                                </div>
                                {(reportType === 'BC007' || reportType === 'BC008') && reportData.pagination && (
                                    <div className="h-10 bg-white border-t border-slate-200 flex items-center justify-between px-4 shrink-0">
                                        <div className="text-[11px] font-bold text-slate-500">
                                            Tổng toàn bộ truy vấn ({Number(reportData.pagination.total_rows||0).toLocaleString()} dòng):
                                            <span className="ml-2 bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-100">{reportData.pagination.total_pages} trang</span>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <button disabled={reportData.pagination.page <= 1} onClick={() => { setFilters(p => ({...p, page: reportData.pagination.page - 1})); setTimeout(loadReportData, 50); }} className="page-btn w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-left" size={16}/></button>
                                            <input type="number" min="1" max={reportData.pagination.total_pages} value={reportData.pagination.page} onChange={e => { const val = parseInt(e.target.value); if (val >= 1 && val <= reportData.pagination.total_pages) { setFilters(p => ({...p, page: val})); setTimeout(loadReportData, 50); } }} className="w-12 bg-transparent text-center font-black text-indigo-600 outline-none" />
                                            <span className="text-[10px] font-black text-slate-400">/ {reportData.pagination.total_pages}</span>
                                            <button disabled={reportData.pagination.page >= reportData.pagination.total_pages} onClick={() => { setFilters(p => ({...p, page: reportData.pagination.page + 1})); setTimeout(loadReportData, 50); }} className="page-btn w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-right" size={16}/></button>
                                        </div>
                                    </div>
                                )}
                            </div>
"""
content = content.replace(end_table_div.strip(), pagination_ui.strip())

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("UI replacements applied.")
