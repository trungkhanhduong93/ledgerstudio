import sys

code = """                                    ) : reportType === 'BC007' ? (
                                        <>
                                        <thead>
                                            <tr>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-24 text-xs">Ngày tháng ghi sổ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-32 text-xs">Số hiệu chứng từ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-24 text-xs">Ngày chứng từ</th>
                                                <th className="border border-slate-300 px-3 py-2 text-left text-xs">Diễn giải</th>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-16 text-xs col-code">TK</th>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-16 text-xs col-code">TK ĐƯ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-right w-32 text-xs col-value">Nợ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-right w-32 text-xs col-value">Có</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {(reportData.data || []).map((row, idx) => (
                                                <tr key={idx} className="hover:bg-slate-50 border-b border-slate-200">
                                                    <td className="border-r border-slate-300 text-center text-xs">{row.tran_date}</td>
                                                    <td className="border-r border-slate-300 px-2 font-bold text-xs">{row.tran_no}</td>
                                                    <td className="border-r border-slate-300 text-center text-xs">{row.tran_date}</td>
                                                    <td className="border-r border-slate-300 px-3 text-xs">{row.description}</td>
                                                    <td className="border-r border-slate-300 text-center font-black text-xs col-code">{row.account_id}</td>
                                                    <td className="border-r border-slate-300 text-center font-black text-xs col-code">{row.contra_account_id}</td>
                                                    <td className="border-r border-slate-300 text-right font-black px-2 text-xs col-value">{row.debit_credit === 'DEB' ? formatNum(row.amount) : ''}</td>
                                                    <td className="text-right font-black px-2 text-xs col-value">{row.debit_credit === 'CRD' ? formatNum(row.amount) : ''}</td>
                                                </tr>
                                            ))}
                                            <tr className="bg-slate-100 font-black">
                                                <td colSpan="6" className="border border-slate-300 px-3 py-2 text-right uppercase tracking-widest text-xs">Cộng lũy kế</td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum((reportData.data || []).filter(r => r.debit_credit === 'DEB').reduce((sum, r) => sum + r.amount, 0))}
                                                </td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">
                                                    {formatNum((reportData.data || []).filter(r => r.debit_credit === 'CRD').reduce((sum, r) => sum + r.amount, 0))}
                                                </td>
                                            </tr>
                                        </tbody>
                                        </>
                                    ) : reportType === 'BC008' ? (
                                        <>
                                        <thead>
                                            <tr>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-24 text-xs">Ngày tháng ghi sổ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-32 text-xs">Số hiệu chứng từ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-24 text-xs">Ngày chứng từ</th>
                                                <th className="border border-slate-300 px-3 py-2 text-left text-xs">Diễn giải</th>
                                                <th className="border border-slate-300 px-2 py-2 text-center w-16 text-xs col-code">TK ĐƯ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-right w-32 text-xs col-value">Nợ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-right w-32 text-xs col-value">Có</th>
                                                <th className="border border-slate-300 px-2 py-2 text-right w-32 text-xs col-value">Dư Nợ</th>
                                                <th className="border border-slate-300 px-2 py-2 text-right w-32 text-xs col-value">Dư Có</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <tr className="bg-slate-50 font-black">
                                                <td colSpan="5" className="border border-slate-300 px-3 py-2 text-right text-xs">SỐ DƯ ĐẦU KỲ</td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">{reportData.opening_balance && reportData.opening_balance.deb ? formatNum(reportData.opening_balance.deb) : ''}</td>
                                                <td className="border border-slate-300 text-right px-2 text-xs col-value">{reportData.opening_balance && reportData.opening_balance.crd ? formatNum(reportData.opening_balance.crd) : ''}</td>
                                            </tr>
                                            {(() => {
                                                let runningDeb = reportData.opening_balance ? reportData.opening_balance.deb : 0;
                                                let runningCrd = reportData.opening_balance ? reportData.opening_balance.crd : 0;
                                                return (reportData.data || []).map((row, idx) => {
                                                    if (row.debit_credit === 'DEB') {
                                                        runningDeb += row.amount;
                                                    } else {
                                                        runningCrd += row.amount;
                                                    }
                                                    const net = runningDeb - runningCrd;
                                                    if (net > 0) { runningDeb = net; runningCrd = 0; }
                                                    else if (net < 0) { runningCrd = Math.abs(net); runningDeb = 0; }
                                                    else { runningDeb = 0; runningCrd = 0; }
                                                    return (
                                                        <tr key={idx} className="hover:bg-slate-50 border-b border-slate-200">
                                                            <td className="border-r border-slate-300 text-center text-xs">{row.tran_date}</td>
                                                            <td className="border-r border-slate-300 px-2 font-bold text-xs">{row.tran_no}</td>
                                                            <td className="border-r border-slate-300 text-center text-xs">{row.tran_date}</td>
                                                            <td className="border-r border-slate-300 px-3 text-xs">{row.description}</td>
                                                            <td className="border-r border-slate-300 text-center font-black text-xs col-code">{row.contra_account_id}</td>
                                                            <td className="border-r border-slate-300 text-right font-black px-2 text-xs col-value">{row.debit_credit === 'DEB' ? formatNum(row.amount) : ''}</td>
                                                            <td className="border-r border-slate-300 text-right font-black px-2 text-xs col-value">{row.debit_credit === 'CRD' ? formatNum(row.amount) : ''}</td>
                                                            <td className="border-r border-slate-300 text-right px-2 text-xs col-value">{runningDeb > 0 ? formatNum(runningDeb) : ''}</td>
                                                            <td className="text-right px-2 text-xs col-value">{runningCrd > 0 ? formatNum(runningCrd) : ''}</td>
                                                        </tr>
                                                    );
                                                });
                                            })()}
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
                                                const openDeb = reportData.opening_balance ? reportData.opening_balance.deb : 0;
                                                const openCrd = reportData.opening_balance ? reportData.opening_balance.crd : 0;
                                                let closeDeb = openDeb + totalSumDeb;
                                                let closeCrd = openCrd + totalSumCrd;
                                                const net = closeDeb - closeCrd;
                                                if (net > 0) { closeDeb = net; closeCrd = 0; }
                                                else if (net < 0) { closeCrd = Math.abs(net); closeDeb = 0; }
                                                else { closeDeb = 0; closeCrd = 0; }
                                                return (
                                                    <tr className="bg-slate-200 font-black">
                                                        <td colSpan="5" className="border border-slate-300 px-3 py-2 text-right uppercase tracking-widest text-xs text-indigo-700">SỐ DƯ CUỐI KỲ</td>
                                                        <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                                        <td className="border border-slate-300 text-right px-2 text-xs col-value"></td>
                                                        <td className="border border-slate-300 text-right px-2 text-xs col-value text-indigo-700">{closeDeb > 0 ? formatNum(closeDeb) : ''}</td>
                                                        <td className="border border-slate-300 text-right px-2 text-xs col-value text-indigo-700">{closeCrd > 0 ? formatNum(closeCrd) : ''}</td>
                                                    </tr>
                                                );
                                            })()}
                                        </tbody>
                                        </>
                                    ) : null}
"""

with open('index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "                                    ) : reportType === 'BC005' ? (" in line:
        start_idx = i
        break

if start_idx != -1:
    for i in range(start_idx, len(lines)):
        if "                                    )}\n" == lines[i] and "</table>" in lines[i+1]:
            end_idx = i
            break
    
    if end_idx != -1:
        lines[end_idx] = code
        with open('index.html', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("Injected OK")
    else:
        print("End tag not found")
else:
    print("Start tag not found")
