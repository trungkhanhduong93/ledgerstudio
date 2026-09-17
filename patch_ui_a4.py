import os

file_path = r"D:\IACC HCM\iPOS ACC\ACC PMKT\LedgerStudio\index.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. CSS Updates
css_scroll_old = """
        .custom-scrollbar::-webkit-scrollbar { width: 5px; height: 5px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
"""
css_scroll_new = """
        .custom-scrollbar::-webkit-scrollbar { width: 8px; height: 8px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 8px; border: 2px solid transparent; background-clip: padding-box; transition: background 0.2s; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; border: 2px solid transparent; background-clip: padding-box; }
"""
if css_scroll_old.strip() in content:
    content = content.replace(css_scroll_old.strip(), css_scroll_new.strip())

css_paper_old = ".report-paper { background: white; width: 297mm; min-height: 210mm; padding: 20mm; margin: 30px auto; box-shadow: 0 25px 70px rgba(0,0,0,0.15); border-radius: 4px; color: #000; }"
css_paper_new = ".report-paper { background: white; width: max-content; min-width: 210mm; max-width: calc(100vw - 64px); min-height: 297mm; padding: 20mm; margin: 30px auto; box-shadow: 0 20px 60px -10px rgba(0,0,0,0.15), 0 10px 30px -10px rgba(0,0,0,0.05); border-radius: 2px; color: #000; border: 1px solid rgba(0,0,0,0.05); transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); }"
if css_paper_old in content:
    content = content.replace(css_paper_old, css_paper_new)

# 2. Add setFilters to ReportTab definition and call
report_tab_sig_old = "const ReportTab = ({ filters, period, setPeriod, meta, onToggleFilter, activeDropdown, setActiveDropdown, reportData: initialReportData, loadReportData, loading, monthList, monthlyData: initialMonthlyData, jobList, jobData: initialJobData, reportType, setReportType, setPendingReportType, setShowClearModal, trialBalanceData, trialBalanceTotal }) => {"
report_tab_sig_new = "const ReportTab = ({ filters, setFilters, period, setPeriod, meta, onToggleFilter, activeDropdown, setActiveDropdown, reportData: initialReportData, loadReportData, loading, monthList, monthlyData: initialMonthlyData, jobList, jobData: initialJobData, reportType, setReportType, setPendingReportType, setShowClearModal, trialBalanceData, trialBalanceTotal }) => {\n            const paperScrollRef = React.useRef(null);"
if report_tab_sig_old in content:
    content = content.replace(report_tab_sig_old, report_tab_sig_new)

report_call_old = "filters={filters}\n                                period={period}"
report_call_new = "filters={filters}\n                                setFilters={setFilters}\n                                period={period}"
if report_call_old in content:
    content = content.replace(report_call_old, report_call_new)

# 3. Add paperScrollRef to the container
container_old = '<div className="flex-1 overflow-auto custom-scrollbar bg-slate-300/40 p-4">'
container_new = '<div className="flex-1 overflow-auto custom-scrollbar bg-slate-200 p-4 relative" ref={paperScrollRef} style={{ scrollBehavior: "smooth" }}>'
if container_old in content:
    content = content.replace(container_old, container_new)

# 4. Inject Floating Navigation Buttons at the end of ReportTab
report_tab_end_old = """
                            <div className="mt-16 text-[8px] text-slate-200 text-right italic tracking-widest uppercase border-t border-slate-50 pt-4">Page {period.value}/{period.year}</div>
                        </div>
                    </div>
                </div>
            );
"""
report_tab_end_new = """
                            <div className="mt-16 text-[8px] text-slate-200 text-right italic tracking-widest uppercase border-t border-slate-50 pt-4">Page {period.value}/{period.year}</div>
                        </div>

                        {/* Floating Action Buttons */}
                        <div className="fixed bottom-10 right-10 flex flex-col gap-3 z-50">
                            <button onClick={() => { if(paperScrollRef.current) paperScrollRef.current.scrollTop = 0; }} className="w-12 h-12 rounded-full bg-white/80 backdrop-blur-md shadow-xl flex items-center justify-center text-slate-600 hover:text-indigo-600 hover:bg-white transition-all duration-300 border border-white hover:scale-110 hover:-translate-y-1" title="Lên đầu trang">
                                <Icon name="arrow-up" size={20} />
                            </button>
                            <button onClick={() => { if(paperScrollRef.current) paperScrollRef.current.scrollTop = paperScrollRef.current.scrollHeight; }} className="w-12 h-12 rounded-full bg-white/80 backdrop-blur-md shadow-xl flex items-center justify-center text-slate-600 hover:text-indigo-600 hover:bg-white transition-all duration-300 border border-white hover:scale-110 hover:translate-y-1" title="Xuống cuối trang">
                                <Icon name="arrow-down" size={20} />
                            </button>
                            {(reportType === 'BC007' || reportType === 'BC008') && reportData.pagination && reportData.pagination.page < reportData.pagination.total_pages && (
                                <button onClick={() => { setFilters(p => ({...p, page: p.page + 1})); setTimeout(loadReportData, 50); }} className="w-12 h-12 rounded-full bg-indigo-600 text-white shadow-[0_10px_25px_rgba(79,70,229,0.4)] flex items-center justify-center hover:bg-indigo-700 transition-all duration-300 mt-2 hover:scale-110" title="Trang tiếp theo">
                                    <Icon name="chevron-right" size={24} />
                                </button>
                            )}
                            {(reportType === 'BC007' || reportType === 'BC008') && reportData.pagination && reportData.pagination.page > 1 && (
                                <button onClick={() => { setFilters(p => ({...p, page: p.page - 1})); setTimeout(loadReportData, 50); }} className="w-12 h-12 rounded-full bg-indigo-600 text-white shadow-[0_10px_25px_rgba(79,70,229,0.4)] flex items-center justify-center hover:bg-indigo-700 transition-all duration-300 hover:scale-110" title="Trang trước">
                                    <Icon name="chevron-left" size={24} />
                                </button>
                            )}
                        </div>

                    </div>
                </div>
            );
"""
if report_tab_end_old.strip() in content:
    content = content.replace(report_tab_end_old.strip(), report_tab_end_new.strip())
else:
    print("Warning: could not find report_tab_end_old")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("UI Patch Applied!")
