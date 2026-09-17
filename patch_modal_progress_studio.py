import sys, os

def patch_studio():
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add exportModal state in ReportTab
    target_state = "const [showJournalExport, setShowJournalExport] = React.useState(false);"
    replacement_state = """const [showJournalExport, setShowJournalExport] = React.useState(false);
            const [exportModal, setExportModal] = React.useState(null); // { open: true, progress: 0-100, status: 'exporting'|'done', path: '', filename: '' }"""

    assert target_state in content, "target_state not found"
    content = content.replace(target_state, replacement_state, 1)

    # 2. Update downloadBlobAndSave function
    target_helper = """            const downloadBlobAndSave = async (apiUrl, defaultFilename) => {"""
    
    new_helper = """            const downloadBlobAndSave = async (apiUrl, defaultFilename) => {
                try {
                    setExportModal({ open: true, progress: 15, status: 'exporting', filename: defaultFilename });
                    const timer1 = setTimeout(() => setExportModal(m => m ? { ...m, progress: 45 } : m), 250);
                    const timer2 = setTimeout(() => setExportModal(m => m ? { ...m, progress: 75 } : m), 600);

                    const r = await fetch(apiUrl);
                    clearTimeout(timer1);
                    clearTimeout(timer2);

                    if (!r.ok) {
                        alert('Lỗi xuất file: ' + r.statusText);
                        setExportModal(null);
                        return;
                    }

                    let filename = defaultFilename;
                    const cd = r.headers.get('Content-Disposition');
                    if (cd) {
                        const match = cd.match(/filename=["']?([^"';]+)["']?/);
                        if (match && match[1]) filename = match[1];
                    }

                    setExportModal({ open: true, progress: 88, status: 'exporting', filename });

                    const blob = await r.blob();
                    const blobUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = blobUrl; a.download = filename;
                    document.body.appendChild(a); a.click(); document.body.removeChild(a);
                    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);

                    const reader = new FileReader();
                    reader.onload = async () => {
                        try {
                            let textContent = reader.result;
                            if (typeof textContent === 'string') {
                                textContent = textContent.replace(/\\r\\r\\n/g, '\\r\\n');
                            }
                            const res = await fetch('/api/save_export', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ filename, content: textContent })
                            }).then(res => res.json());

                            if (res.status === 'ok') {
                                setExportModal({ open: true, progress: 100, status: 'done', path: res.path, filename: res.filename });
                            } else {
                                setExportModal({ open: true, progress: 100, status: 'done', path: '', filename });
                            }
                        } catch (e) {
                            setExportModal({ open: true, progress: 100, status: 'done', path: '', filename });
                        }
                    };
                    reader.readAsText(blob);
                } catch (err) {
                    alert('Lỗi xuất file: ' + err.message);
                    setExportModal(null);
                }
            };"""

    # Replace old downloadBlobAndSave block up to end of function
    pos_old = content.find("const downloadBlobAndSave = async (apiUrl, defaultFilename) => {")
    pos_end = content.find("const exportJournalCsv = (mode) => {", pos_old)
    assert pos_old > 0 and pos_end > 0, "downloadBlobAndSave boundaries not found"
    
    content = content[:pos_old] + new_helper + "\n\n" + content[pos_end:]

    # 3. Update exportReportXls in ReportTab
    pos_xls = content.find("const exportReportXls = () => {")
    pos_xls_end = content.find("const exportJournalCsv = (mode) => {", pos_xls)
    if pos_xls_end < 0:
        pos_xls_end = content.find("const exportToExcel = () => {", pos_xls)

    # Replace inside exportReportXls
    target_xls_save = """                fetch('/api/save_export', {"""
    pos_save = content.find(target_xls_save, pos_xls)
    pos_save_end = content.find("});\n            };", pos_save)

    old_xls_block = content[pos_save:pos_save_end + 18]
    new_xls_block = """setExportModal({ open: true, progress: 35, status: 'exporting', filename: fname });

                const blob = new Blob(['\\ufeff' + html], { type: 'application/vnd.ms-excel' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = fname;
                document.body.appendChild(a); a.click(); document.body.removeChild(a);
                setTimeout(() => URL.revokeObjectURL(url), 1000);

                setExportModal({ open: true, progress: 75, status: 'exporting', filename: fname });

                fetch('/api/save_export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename: fname, content: html })
                }).then(r => r.json()).then(res => {
                    if (res.status === 'ok') {
                        setExportModal({ open: true, progress: 100, status: 'done', path: res.path, filename: res.filename });
                    } else {
                        setExportModal({ open: true, progress: 100, status: 'done', path: '', filename: fname });
                    }
                }).catch(() => {
                    setExportModal({ open: true, progress: 100, status: 'done', path: '', filename: fname });
                });
            };"""

    content = content.replace(old_xls_block, new_xls_block, 1)

    # 4. Add Export Progress Modal JSX to end of ReportTab render
    modal_jsx = """
                        {/* MODAL TIẾN TRÌNH XUẤT EXCEL (0-100% -> MỞ FILE / MỞ FOLDER) */}
                        {exportModal && exportModal.open && (
                            <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-[99999] px-4 animate-backdrop" onClick={() => { if (exportModal.status === 'done') setExportModal(null); }}>
                                <div className="bg-white rounded-3xl p-8 max-w-md w-full shadow-2xl border border-slate-100 animate-modal" onClick={e => e.stopPropagation()}>
                                    {exportModal.status === 'exporting' ? (
                                        <div className="space-y-5">
                                            <div className="flex items-center gap-4">
                                                <div className="relative shrink-0">
                                                    <div className="w-12 h-12 border-4 border-indigo-100 rounded-full"></div>
                                                    <div className="w-12 h-12 border-4 border-indigo-600 rounded-full border-t-transparent animate-spin absolute top-0 left-0"></div>
                                                    <Icon name="file-text" size={20} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-indigo-600"/>
                                                </div>
                                                <div>
                                                    <h3 className="text-[15px] font-black text-slate-900 uppercase tracking-tight">Đang xuất file Excel</h3>
                                                    <p className="text-[11px] font-bold text-slate-400 mt-0.5 truncate max-w-[240px]">{exportModal.filename}</p>
                                                </div>
                                            </div>

                                            <div className="space-y-1.5">
                                                <div className="flex justify-between items-center text-xs font-black">
                                                    <span className="text-slate-500 uppercase tracking-widest text-[10px]">Tiến trình</span>
                                                    <span className="text-indigo-600 text-sm tabular-nums font-mono">{exportModal.progress}%</span>
                                                </div>
                                                <div className="w-full h-3 bg-slate-100 rounded-full overflow-hidden p-0.5 border border-slate-100">
                                                    <div 
                                                        className="h-full bg-gradient-to-r from-indigo-500 to-indigo-600 rounded-full transition-all duration-300 shadow-sm"
                                                        style={{ width: `${exportModal.progress}%` }}
                                                    ></div>
                                                </div>
                                            </div>

                                            <div className="text-[10px] font-bold text-slate-400 text-center italic">
                                                Đang kết xuất dữ liệu, vui lòng chờ trong giây lát...
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="space-y-5">
                                            <div className="flex items-center gap-3">
                                                <div className="w-12 h-12 rounded-2xl bg-emerald-100 text-emerald-600 flex items-center justify-center shrink-0">
                                                    <Icon name="check" size={24} />
                                                </div>
                                                <div className="overflow-hidden">
                                                    <h3 className="font-black text-slate-900 text-base leading-tight">Xuất Excel hoàn tất!</h3>
                                                    <p className="text-[11px] font-bold text-slate-400 mt-0.5 truncate">{exportModal.filename}</p>
                                                </div>
                                            </div>

                                            <div className="space-y-1.5">
                                                <div className="flex justify-between items-center text-xs font-black">
                                                    <span className="text-slate-500 uppercase tracking-widest text-[10px]">Hoàn thành</span>
                                                    <span className="text-emerald-600 text-sm tabular-nums font-mono">100%</span>
                                                </div>
                                                <div className="w-full h-3 bg-emerald-100 rounded-full overflow-hidden p-0.5">
                                                    <div className="h-full bg-emerald-600 rounded-full w-full"></div>
                                                </div>
                                            </div>

                                            <div className="space-y-2 pt-2">
                                                {exportModal.path && (
                                                    <button 
                                                        onClick={async () => {
                                                            await fetch('/api/open_file', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: exportModal.path }) });
                                                            setExportModal(null);
                                                        }} 
                                                        className="w-full bg-emerald-600 text-white py-3 rounded-2xl font-bold text-xs hover:bg-emerald-700 transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/20 uppercase tracking-wider"
                                                    >
                                                        <Icon name="external-link" size={14} /> Mở file ngay
                                                    </button>
                                                )}
                                                {exportModal.path && (
                                                    <button 
                                                        onClick={async () => {
                                                            await fetch('/api/open_folder', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: exportModal.path }) });
                                                            setExportModal(null);
                                                        }} 
                                                        className="w-full bg-slate-100 text-slate-700 py-3 rounded-2xl font-bold text-xs hover:bg-slate-200 transition-all flex items-center justify-center gap-2 uppercase tracking-wider"
                                                    >
                                                        <Icon name="folder" size={14} /> Mở thư mục chứa file
                                                    </button>
                                                )}
                                                <button 
                                                    onClick={() => setExportModal(null)} 
                                                    className="w-full text-slate-400 py-2 font-bold text-xs hover:text-slate-600 transition-all text-center uppercase tracking-widest"
                                                >
                                                    Đóng
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
"""

    pos_report_tab_end = content.find("/* BC013 — chọn kiểu xuất Excel */", pos_xls)
    if pos_report_tab_end < 0:
        pos_report_tab_end = content.find("{showVatSalesExport && (", pos_xls)

    assert pos_report_tab_end > 0, "pos_report_tab_end not found"
    content = content[:pos_report_tab_end] + modal_jsx + "\n\n" + content[pos_report_tab_end:]

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)

    print("Studio index.html patched with progress modal successfully!")

if __name__ == "__main__":
    patch_studio()
