import sys

def patch():
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # Targets 1-12 are already done or idempotent if checked:
    if "BC013" not in content:
        # 1. REPORT_TYPES
        target1 = "const REPORT_TYPES = ["
        replacement1 = "const REPORT_TYPES = [\n            { id: 'BC013', name: '6.2 - BẢNG KÊ HÓA ĐƠN, CHỨNG TỪ HÀNG HÓA, DỊCH VỤ BÁN RA' },"
        assert target1 in content, "target1 not found"
        content = content.replace(target1, replacement1, 1)

        # 2. REPORT_FILE
        target2 = "BC012: 'BC012_So_Tien_Mat_Va_Tien_Ngan_Hang'"
        replacement2 = "BC012: 'BC012_So_Tien_Mat_Va_Tien_Ngan_Hang',\n                BC013: '6.2_Bang_Ke_Hoa_Don_Hang_Hoa_Dich_Vu_Ban_Ra'"
        assert target2 in content, "target2 not found"
        content = content.replace(target2, replacement2, 1)

        # 3. ReportTab signature
        target3 = "const ReportTab = ({ filters, setFilters, period, setPeriod, meta, onToggleFilter, activeDropdown, setActiveDropdown, reportData: initialReportData, loadReportData, loading, monthList, monthlyData: initialMonthlyData, jobList, jobData: initialJobData, reportType, setReportType, setPendingReportType, setShowClearModal, trialBalanceData, trialBalanceTotal, cashBookData }) => {"
        replacement3 = "const ReportTab = ({ filters, setFilters, period, setPeriod, meta, onToggleFilter, activeDropdown, setActiveDropdown, reportData: initialReportData, loadReportData, loading, monthList, monthlyData: initialMonthlyData, jobList, jobData: initialJobData, reportType, setReportType, setPendingReportType, setShowClearModal, trialBalanceData, trialBalanceTotal, cashBookData, vatSalesTotals }) => {"
        assert target3 in content, "target3 not found"
        content = content.replace(target3, replacement3, 1)

        # 4. App state
        target4 = "const [cashBookData, setCashBookData] = useState({ rows: [], pagination: { total_rows: 0, total_pages: 1, page: 1 } });"
        replacement4 = "const [cashBookData, setCashBookData] = useState({ rows: [], pagination: { total_rows: 0, total_pages: 1, page: 1 } });\n        const [vatSalesTotals, setVatSalesTotals] = useState({ total_amount_item: 0, taxable_amount_item: 0, total_vat_amount: 0 });"
        assert target4 in content, "target4 not found"
        content = content.replace(target4, replacement4, 1)

        # 5. loadReportData
        target5 = "} else if (reportType === 'BC012') {"
        replacement5 = "} else if (reportType === 'BC013') {\n                    const q2 = new URLSearchParams({ from_date: filters.from_date, to_date: filters.to_date, org_ids: filters.org_ids.join(','), acc_ids: filters.acc_ids.join(',') });\n                    const r = await fetch(`/api/vat_sales_report?${q2.toString()}`, { signal: abortRef.current.signal });\n                    if (r.status === 401) { setIsLoggedIn(false); return; }\n                    const res = await r.json();\n                    if (res.status === 'ok') {\n                        setReportData(res.data || []);\n                        setVatSalesTotals(res.totals || { total_amount_item: 0, taxable_amount_item: 0, total_vat_amount: 0 });\n                    } else {\n                        alert('Lỗi xem bảng kê bán ra: ' + (res.message || 'không có dữ liệu'));\n                    }\n                } else if (reportType === 'BC012') {"
        assert target5 in content, "target5 not found"
        content = content.replace(target5, replacement5, 1)

        # 6. Filter bar account dropdown condition
        target6 = "{(reportType === 'BC008' || reportType === 'BC011' || reportType === 'BC012') ? ("
        replacement6 = "{(reportType === 'BC008' || reportType === 'BC011' || reportType === 'BC012' || reportType === 'BC013') ? ("
        assert target6 in content, "target6 not found"
        content = content.replace(target6, replacement6, 1)

        # 7. paper-landscape list
        target7 = "<div className={`report-paper ${['BC001', 'BC002', 'BC003', 'BC004', 'BC006', 'BC007', 'BC011', 'BC012'].includes(reportType) ? 'paper-landscape' : 'paper-portrait'}`}>"
        replacement7 = "<div className={`report-paper ${['BC001', 'BC002', 'BC003', 'BC004', 'BC006', 'BC007', 'BC011', 'BC012', 'BC013'].includes(reportType) ? 'paper-landscape' : 'paper-portrait'}`}>"
        assert target7 in content, "target7 not found"
        content = content.replace(target7, replacement7, 1)

        # 8. Report badge
        target8 = "reportType === 'BC012' ? 'Mẫu S07 - DN' : 'Mẫu B02 - DN'"
        replacement8 = "reportType === 'BC012' ? 'Mẫu S07 - DN' : reportType === 'BC013' ? 'Mẫu 6.2 - GTGT' : 'Mẫu B02 - DN'"
        assert target8 in content, "target8 not found"
        content = content.replace(target8, replacement8, 1)

        # 9. Title
        target9 = "reportType === 'BC012' ? 'SỔ TIỀN MẶT VÀ TIỀN NGÂN HÀNG'"
        replacement9 = "reportType === 'BC013' ? '6.2 - BẢNG KÊ HÓA ĐƠN, CHỨNG TỪ HÀNG HÓA, DỊCH VỤ BÁN RA' : reportType === 'BC012' ? 'SỔ TIỀN MẶT VÀ TIỀN NGÂN HÀNG'"
        assert target9 in content, "target9 not found"
        content = content.replace(target9, replacement9, 1)

        # 10. Subtitle Account ID for BC013
        target10 = "{reportType === 'BC012' && ("
        replacement10 = "{reportType === 'BC013' && (\n                                    <div className=\"text-[10px] font-bold text-slate-600 uppercase\">Tài khoản: {filters.acc_ids.length > 0 ? filters.acc_ids.join(', ') : '33311'}-</div>\n                                )}\n                                {reportType === 'BC012' && ("
        assert target10 in content, "target10 not found"
        content = content.replace(target10, replacement10, 1)

        # 11. Table content for BC013
        target11 = ") : reportType === 'BC005' ? ("
        replacement11 = """) : reportType === 'BC013' ? (
                                    <>
                                        <thead>
                                            <tr>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center w-10 text-xs font-bold">TT</th>
                                                <th colSpan="3" className="border border-slate-300 px-2 py-2 text-center text-xs font-bold">Hóa đơn, chứng từ, biên lai nộp thuế</th>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center text-xs font-bold">Tên người bán</th>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center text-xs font-bold">Mã số thuế người mua</th>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center text-xs font-bold">Mặt hàng</th>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center text-xs font-bold col-value">Doanh số bán chưa có thuế</th>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center w-16 text-xs font-bold">Thuế suất (%)</th>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center text-xs font-bold col-value">Thuế GTGT</th>
                                                <th rowSpan="2" className="border border-slate-300 px-2 py-2 text-center text-xs font-bold">Ghi chú</th>
                                            </tr>
                                            <tr>
                                                <th className="border border-slate-300 px-2 py-1 text-center text-[11px] font-bold">Ký hiệu hóa đơn</th>
                                                <th className="border border-slate-300 px-2 py-1 text-center text-[11px] font-bold">Số hóa đơn</th>
                                                <th className="border border-slate-300 px-2 py-1 text-center text-[11px] font-bold">Ngày, tháng, năm phát hành</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {(Array.isArray(reportData) ? reportData : []).map((row, idx) => (
                                                <tr key={idx} className="hover:bg-slate-50 border-b border-slate-200">
                                                    <td className="border-r border-slate-300 text-center text-xs">{idx + 1}</td>
                                                    <td className="border-r border-slate-300 text-center text-xs col-code">{row.serie}</td>
                                                    <td className="border-r border-slate-300 text-center font-bold text-xs col-code">{row.no}</td>
                                                    <td className="border-r border-slate-300 text-center text-xs">{row.date}</td>
                                                    <td className="border-r border-slate-300 px-2 text-xs">{row.seller}</td>
                                                    <td className="border-r border-slate-300 text-center text-xs col-code">{row.tax_code}</td>
                                                    <td className="border-r border-slate-300 px-2 text-xs">{row.item}</td>
                                                    <td className="border-r border-slate-300 text-right px-2 text-xs col-value">{formatNum(row.amount_item)}</td>
                                                    <td className="border-r border-slate-300 text-center text-xs">{row.tax_rate !== undefined ? `${row.tax_rate}%` : '0%'}</td>
                                                    <td className="border-r border-slate-300 text-right px-2 text-xs col-value">{formatNum(row.tax_amount)}</td>
                                                    <td className="px-2 text-xs">{row.comments}</td>
                                                </tr>
                                            ))}
                                            {(Array.isArray(reportData) && reportData.length === 0) && (
                                                <tr>
                                                    <td colSpan="11" className="text-center py-8 text-slate-400 text-xs italic">Không có dữ liệu trong kỳ báo cáo đã chọn</td>
                                                </tr>
                                            )}
                                            {(Array.isArray(reportData) && reportData.length > 0) && (
                                                <tr className="font-bold bg-slate-100/80 border-t border-b border-slate-400">
                                                    <td colSpan="7" className="border-r border-slate-300 text-center text-xs">Tổng cộng</td>
                                                    <td className="border-r border-slate-300 text-right px-2 text-xs col-value">{formatNum(vatSalesTotals.total_amount_item)}</td>
                                                    <td className="border-r border-slate-300"></td>
                                                    <td className="border-r border-slate-300 text-right px-2 text-xs col-value">{formatNum(vatSalesTotals.total_vat_amount)}</td>
                                                    <td></td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </>
                                ) : reportType === 'BC005' ? ("""
        assert target11 in content, "target11 not found"
        content = content.replace(target11, replacement11, 1)

        # 12. Footer signature
        target12 = '                            <div className="mt-12">\n                                <div className="grid grid-cols-3 gap-10 text-center">'
        replacement12 = """{reportType === 'BC013' ? (
                                <div className="mt-6 text-xs text-slate-900 font-semibold">
                                    <div className="space-y-1.5 ml-4">
                                        <div>Tổng doanh thu hàng hoá dịch vụ bán ra: <span className="font-bold">{formatNum(vatSalesTotals.total_amount_item)}</span></div>
                                        <div>Tổng doanh thu hàng hoá dịch vụ bán ra chịu thuế GTGT: <span className="font-bold">{formatNum(vatSalesTotals.taxable_amount_item)}</span></div>
                                        <div>Thuế GTGT của hàng hoá dịch vụ bán ra: <span className="font-bold">{formatNum(vatSalesTotals.total_vat_amount)}</span></div>
                                    </div>
                                    <div className="mt-8 flex justify-end">
                                        <div className="text-center text-xs pr-8">
                                            <div className="italic text-slate-600">
                                                , Ngày {new Date().getDate()} Tháng {new Date().getMonth() + 1} Năm {new Date().getFullYear()}
                                            </div>
                                            <div className="font-bold mt-1 text-slate-800">
                                                Người nộp thuế (hoặc đại diện hợp phát của người nộp thuế)
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="mt-12">
                                <div className="grid grid-cols-3 gap-10 text-center">"""
        assert target12 in content, "target12 not found"
        content = content.replace(target12, replacement12, 1)

    # 13. App ReportTab call
    target13 = "                                cashBookData={cashBookData}\n                            />"
    replacement13 = "                                cashBookData={cashBookData}\n                                vatSalesTotals={vatSalesTotals}\n                            />"
    assert target13 in content, "target13 not found"
    content = content.replace(target13, replacement13, 1)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patch successful!")

if __name__ == "__main__":
    patch()
