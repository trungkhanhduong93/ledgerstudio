
        const { useState, useEffect, useRef, useCallback, useMemo, memo } = React;

        // ===== Global format helpers — tránh tạo closure mỗi render =====
        const fmtNum = (v, d = 2) => {
            if (v === null || v === undefined || v === '') return '';
            const n = Number(v);
            return Number.isFinite(n) ? n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }) : '';
        };
        

        const fmtInt = (v) => {
            if (v === null || v === undefined || v === '') return '';
            const n = Number(v);
            return Number.isFinite(n) ? Math.round(n).toLocaleString('en-US') : '';
        };
        
        const { createPortal } = ReactDOM;


        // Chunked spacer rows for virtual scroll - splits large heights into multiple <tr>
        // to avoid browser ignoring large single-row heights in <table>
        // Dùng SVG làm spacer: SVG là replaced element, browser LUÔN respect height attribute
        // dù rất lớn (1M+ px) — tránh được trường hợp <tr style="height"> bị collapse trong table layout
        const VirtualSpacer = ({ height }) => {
            if (height <= 0) return null;
            return (
                <tr aria-hidden="true">
                    <td colSpan="100" style={{ padding: 0, border: 0, lineHeight: 0, fontSize: 0, verticalAlign: 'top' }}>
                        <svg width="1" height={height} style={{ display: 'block' }} aria-hidden="true" />
                    </td>
                </tr>
            );
        };

        function useVirtualScroll(totalItems, itemHeight, containerRef) {
            const [scrollTop, setScrollTop] = React.useState(0);
            const [containerHeight, setContainerHeight] = React.useState(() => (typeof window !== 'undefined' ? window.innerHeight : 800));

            // Gắn scroll listener + ResizeObserver — KHÔNG phụ thuộc totalItems để tránh tear-down lặp
            React.useEffect(() => {
                const container = containerRef.current;
                if (!container) return;
                const handleScroll = () => setScrollTop(container.scrollTop);
                container.addEventListener('scroll', handleScroll, { passive: true });

                const measure = () => {
                    const h = container.clientHeight || container.getBoundingClientRect().height;
                    if (h > 0) setContainerHeight(h);
                };
                const ro = new ResizeObserver(() => measure());
                ro.observe(container);

                measure();
                const raf1 = requestAnimationFrame(measure);
                const raf2 = requestAnimationFrame(() => requestAnimationFrame(measure));
                const onResize = () => measure();
                window.addEventListener('resize', onResize);

                return () => {
                    container.removeEventListener('scroll', handleScroll);
                    ro.disconnect();
                    cancelAnimationFrame(raf1);
                    cancelAnimationFrame(raf2);
                    window.removeEventListener('resize', onResize);
                };
            // eslint-disable-next-line react-hooks/exhaustive-deps
            }, [containerRef.current]);

            // Khi data đổi (totalItems thay đổi) → reset scroll về đầu + đo lại để tránh state lệch DOM
            React.useLayoutEffect(() => {
                const container = containerRef.current;
                if (!container) return;
                container.scrollTop = 0;
                setScrollTop(0);
                const h = container.clientHeight || container.getBoundingClientRect().height;
                if (h > 0) setContainerHeight(h);
            // eslint-disable-next-line react-hooks/exhaustive-deps
            }, [totalItems]);

            const overscan = 50;
            let startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
            let endIndex = Math.min(totalItems - 1, Math.floor((scrollTop + containerHeight) / itemHeight) + overscan);
            if(totalItems === 0) { startIndex=0; endIndex=-1; }
            
            const topPadding = startIndex * itemHeight;
            const totalHeight = totalItems * itemHeight;
            const bottomPadding = Math.max(0, totalHeight - (endIndex + 1) * itemHeight);
            
            return { startIndex, endIndex, topPadding, bottomPadding, totalHeight };
        }

        // State global cho expand/collapse node
        const expandState = new Map();

        function buildGroupedData(rawData, groupCols, sumFields) {
            if (!groupCols || groupCols.length === 0) return rawData;
            const rootGroups = new Map();
            for(let i=0; i<rawData.length; i++) {
                const row = rawData[i];
                let currentMap = rootGroups;
                let parentKey = '';
                for(let j=0; j<groupCols.length; j++) {
                    const col = groupCols[j];
                    const val = row[col] || '(Trống)';
                    
                    let key = parentKey ? parentKey + '|' + val : val;
                    parentKey = key; // Save for next level

                    if (!currentMap.has(key)) {
                        let exp = expandState.has(key) ? expandState.get(key) : true;
                        currentMap.set(key, { id: key, name: val, col, level: j, sums: {}, children: [], map: new Map(), expanded: exp });
                        if(sumFields) sumFields.forEach(f => currentMap.get(key).sums[f] = 0);
                    }
                    const node = currentMap.get(key);
                    if(sumFields) {
                        if(row.DEBIT_CREDIT === 'DEB') node.sums.DEBIT = (node.sums.DEBIT || 0) + (parseFloat(row.AMOUNT) || 0);
                        if(row.DEBIT_CREDIT === 'CRD') node.sums.CREDIT = (node.sums.CREDIT || 0) + (parseFloat(row.AMOUNT) || 0);
                        if(row.TOTAL_AMOUNT) node.sums.TOTAL_AMOUNT = (node.sums.TOTAL_AMOUNT || 0) + (parseFloat(row.TOTAL_AMOUNT) || 0);
                        if(row.AMOUNT && row.DEBIT_CREDIT !== 'DEB' && row.DEBIT_CREDIT !== 'CRD') node.sums.AMOUNT = (node.sums.AMOUNT || 0) + (parseFloat(row.AMOUNT) || 0);
                    }
                    
                    if (j === groupCols.length - 1) {
                        node.children.push(row);
                    } else {
                        currentMap = node.map;
                    }
                }
            }
            const flat = [];
            const flatten = (map) => {
                for (const [key, node] of map.entries()) {
                    flat.push({ isGroup: true, ...node });
                    if (node.expanded) {
                        if (node.children.length > 0) flat.push(...node.children);
                        else flatten(node.map);
                    }
                }
            };
            flatten(rootGroups);
            return flat;
        }

        const LedgerGroupRow = ({ node, toggleExpand }) => {
            return (
                <tr className={`border-b border-slate-200 font-bold text-[11px] cursor-pointer transition-colors ${node.level === 0 ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'bg-indigo-50 text-indigo-900 hover:bg-indigo-100'}`} onClick={() => toggleExpand(node.id)}>
                    <td colSpan={8} className="px-4 py-1.5 border-r border-indigo-200/30 whitespace-nowrap">
                        <div className="flex items-center gap-2" style={{ paddingLeft: `${node.level * 20}px` }}>
                            <span className={`inline-flex items-center justify-center w-3 h-3 border rounded-sm font-mono text-[9px] leading-none ${node.level === 0 ? 'border-indigo-400 bg-indigo-500' : 'border-indigo-300 bg-white'}`}>
                                {node.expanded ? '-' : '+'}
                            </span>
                            <span>{node.col}: {node.name}</span>
                            <span className={`text-[10px] ml-2 ${node.level === 0 ? 'text-indigo-200' : 'text-indigo-400'}`}>({node.children ? node.children.length : 0} dòng)</span>
                        </div>
                    </td>
                    <td className={`border-r border-indigo-200/30 text-right font-mono px-2 ${node.level === 0 ? 'text-white' : 'text-indigo-700'}`}>
                        {node.sums.DEBIT !== undefined && node.sums.DEBIT !== 0 ? node.sums.DEBIT.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}) : ''}
                    </td>
                    <td className={`border-r border-indigo-200/30 text-right font-mono px-2 ${node.level === 0 ? 'text-white' : 'text-indigo-700'}`}>
                        {node.sums.CREDIT !== undefined && node.sums.CREDIT !== 0 ? node.sums.CREDIT.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}) : ''}
                    </td>
                    <td colSpan={100}></td>
                </tr>
            );
        };

        const PurchaseGroupRow = ({ node, toggleExpand }) => {
            return (
                <tr className={`border-b border-slate-200 font-bold text-[11px] cursor-pointer transition-colors ${node.level === 0 ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'bg-indigo-50 text-indigo-900 hover:bg-indigo-100'}`} onClick={() => toggleExpand(node.id)}>
                    <td colSpan={23} className="px-4 py-1.5 border-r border-indigo-200/30 whitespace-nowrap">
                        <div className="flex items-center gap-2" style={{ paddingLeft: `${node.level * 20}px` }}>
                            <span className={`inline-flex items-center justify-center w-3 h-3 border rounded-sm font-mono text-[9px] leading-none ${node.level === 0 ? 'border-indigo-400 bg-indigo-500' : 'border-indigo-300 bg-white'}`}>
                                {node.expanded ? '-' : '+'}
                            </span>
                            <span>{node.col}: {node.name}</span>
                            <span className={`text-[10px] ml-2 ${node.level === 0 ? 'text-indigo-200' : 'text-indigo-400'}`}>({node.children ? node.children.length : 0} dòng)</span>
                        </div>
                    </td>
                    <td className={`border-r border-indigo-200/30 text-right font-mono font-black px-2 ${node.level === 0 ? 'text-white' : 'text-emerald-600'}`}>
                        {node.sums.TOTAL_AMOUNT !== undefined && node.sums.TOTAL_AMOUNT !== 0 ? node.sums.TOTAL_AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0}) : ''}
                    </td>
                    <td colSpan={100}></td>
                </tr>
            );
        };

        const WarehouseGroupRow = ({ node, toggleExpand }) => {
            return (
                <tr className={`border-b border-slate-200 font-bold text-[11px] cursor-pointer transition-colors ${node.level === 0 ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'bg-indigo-50 text-indigo-900 hover:bg-indigo-100'}`} onClick={() => toggleExpand(node.id)}>
                    <td colSpan={19} className="px-4 py-1.5 border-r border-indigo-200/30 whitespace-nowrap">
                        <div className="flex items-center gap-2" style={{ paddingLeft: `${node.level * 20}px` }}>
                            <span className={`inline-flex items-center justify-center w-3 h-3 border rounded-sm font-mono text-[9px] leading-none ${node.level === 0 ? 'border-indigo-400 bg-indigo-500' : 'border-indigo-300 bg-white'}`}>
                                {node.expanded ? '-' : '+'}
                            </span>
                            <span>{node.col}: {node.name}</span>
                            <span className={`text-[10px] ml-2 ${node.level === 0 ? 'text-indigo-200' : 'text-indigo-400'}`}>({node.children ? node.children.length : 0} dòng)</span>
                        </div>
                    </td>
                    <td className={`border-r border-indigo-200/30 text-right font-mono font-black px-2 ${node.level === 0 ? 'text-white' : 'text-emerald-600'}`}>
                        {node.sums.AMOUNT !== undefined && node.sums.AMOUNT !== 0 ? node.sums.AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0}) : ''}
                    </td>
                    <td colSpan={100}></td>
                </tr>
            );
        };


        // Debounce hook — trì hoãn callback cho đến khi người dùng ngừng gõ
        function useDebounce(value, delay) {
            const [debounced, setDebounced] = useState(value);
            useEffect(() => {
                const t = setTimeout(() => setDebounced(value), delay);
                return () => clearTimeout(t);
            }, [value, delay]);
            return debounced;
        }

        const Icon = ({ name, size = 12, className = "" }) => {
            const icons = {
                "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
                "chevron-down": '<path d="m6 9 6 6 6-6"/>',
                "chevron-left": '<path d="m15 18-6-6 6-6"/>',
                "chevron-right": '<path d="m9 18 6-6 6-6"/>',
                "calendar": '<rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/>',
                "loader": '<path d="M12 2v4"/><path d="m16.2 4.2 2.8 2.8"/><path d="M18 12h4"/><path d="m16.2 19.8 2.8-2.8"/><path d="M12 18v4"/><path d="m4.2 19.8 2.8-2.8"/><path d="M2 12h4"/><path d="m4.2 4.2 2.8 2.8"/>',
                "file-text": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/>',
                "table": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/><path d="M15 3v18"/>',
                "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
                "file-spreadsheet": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><path d="M8 13h2v7H8z"/><path d="M12 15h2v5h-2z"/><path d="M16 11h2v9h-2z"/>',
                "check": '<polyline points="20 6 9 17 4 12"/>',
                "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>',
                "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
                "lock": '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
                "sliders": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
                "chevron-up": '<path d="m18 15-6-6-6 6"/>',
                "arrow-up": '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
                "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
                "arrows-updown": '<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>'
            };
            return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={className} dangerouslySetInnerHTML={{ __html: icons[name] || '' }} />;
        };

        const IOSDatePicker = ({ label, value, onChange, disabled }) => {
            const [isOpen, setIsOpen] = useState(false);
            const [displayDate, setDisplayDate] = useState(new Date());
            const [pos, setPos] = useState({ top: 0, left: 0 });
            const buttonRef = useRef(null);
            const calendarRef = useRef(null);

            const parseDate = (str) => {
                if (!str) return null;
                const [d, m, y] = str.split('/').map(Number);
                return new Date(y, m - 1, d);
            };
            const selectedDate = parseDate(value);
            const today = new Date(); today.setHours(0,0,0,0);

            useEffect(() => {
                if (value) {
                    const d = parseDate(value);
                    if (d) setDisplayDate(new Date(d.getFullYear(), d.getMonth(), 1));
                }
            }, [isOpen]);

            const updatePos = () => {
                if (buttonRef.current) {
                    const r = buttonRef.current.getBoundingClientRect();
                    const calWidth = 300, calHeight = 400;
                    let left = r.left;
                    if (left + calWidth > window.innerWidth - 8) left = window.innerWidth - calWidth - 8;
                    let top = (r.bottom + calHeight + 6 > window.innerHeight) ? r.top - calHeight - 6 : r.bottom + 6;
                    setPos({ top: Math.max(8, top), left: Math.max(8, left) });
                }
            };

            useEffect(() => {
                if (!isOpen) return;
                const onDown = (e) => { if (!calendarRef.current?.contains(e.target) && !buttonRef.current?.contains(e.target)) setIsOpen(false); };
                document.addEventListener('mousedown', onDown);
                window.addEventListener('scroll', updatePos, true);
                window.addEventListener('resize', updatePos);
                return () => { document.removeEventListener('mousedown', onDown); window.removeEventListener('scroll', updatePos, true); window.removeEventListener('resize', updatePos); };
            }, [isOpen]);

            const daysInMonth = new Date(displayDate.getFullYear(), displayDate.getMonth() + 1, 0).getDate();
            const rawFirst = new Date(displayDate.getFullYear(), displayDate.getMonth(), 1).getDay();
            const firstDay = rawFirst === 0 ? 6 : rawFirst - 1;

            const handleDateSelect = (day) => {
                const y = displayDate.getFullYear(), m = String(displayDate.getMonth() + 1).padStart(2, '0'), d = String(day).padStart(2, '0');
                onChange(`${d}/${m}/${y}`);
                setIsOpen(false);
            };

            const monthNames = ['Tháng 1','Tháng 2','Tháng 3','Tháng 4','Tháng 5','Tháng 6','Tháng 7','Tháng 8','Tháng 9','Tháng 10','Tháng 11','Tháng 12'];
            const weekDays = ['T2','T3','T4','T5','T6','T7','CN'];

            return (
                <div className="relative">
                    <div className="label-text">{label}</div>
                    <button
                        ref={buttonRef}
                        disabled={disabled}
                        onClick={() => { if (!isOpen) updatePos(); setIsOpen(!isOpen); }}
                        className={`filter-control justify-between font-bold ${isOpen ? 'active ring-2 ring-indigo-100 border-indigo-400' : ''} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <span className="truncate">{value || 'Chọn ngày'}</span>
                        <Icon name="calendar" size={10} className={`${isOpen ? 'text-indigo-600' : 'text-slate-400'}`} />
                    </button>
                    {isOpen && createPortal(
                        <div ref={calendarRef} style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 999999, width: 300, background: '#fff', borderRadius: 16, boxShadow: '0 20px 60px rgba(0,0,0,0.18), 0 0 0 0.5px rgba(0,0,0,0.06)', overflow: 'hidden', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif' }}>
                            <div style={{ background: '#f2f2f7', borderBottom: '1px solid rgba(0,0,0,0.08)', padding: '12px 12px 10px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
                                    <button onClick={() => setDisplayDate(new Date(displayDate.getFullYear(), displayDate.getMonth() - 1, 1))} style={{ padding: '4px 8px', borderRadius: 8, border: 'none', background: 'transparent', cursor: 'pointer', color: '#4f46e5' }}><Icon name="chevron-left" size={16}/></button>
                                    <div style={{ flex: 1, textAlign: 'center' }}><span style={{ fontSize: 15, fontWeight: 700, color: '#1c1c1e' }}>{monthNames[displayDate.getMonth()]} {displayDate.getFullYear()}</span></div>
                                    <button onClick={() => setDisplayDate(new Date(displayDate.getFullYear(), displayDate.getMonth() + 1, 1))} style={{ padding: '4px 8px', borderRadius: 8, border: 'none', background: 'transparent', cursor: 'pointer', color: '#4f46e5' }}><Icon name="chevron-right" size={16}/></button>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)' }}>{weekDays.map((d, i) => (<div key={d} style={{ textAlign: 'center', fontSize: 10, fontWeight: 700, padding: '2px 0', color: i === 6 ? '#ff3b30' : 'rgba(0,0,0,0.4)' }}>{d}</div>))}</div>
                            </div>
                            <div style={{ padding: '8px 12px 6px' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px 0' }}>
                                    {Array(firstDay).fill(null).map((_, i) => <div key={`e${i}`} style={{ height: 34 }} />)}
                                    {Array.from({ length: daysInMonth }, (_, i) => i + 1).map(day => {
                                        const dObj = new Date(displayDate.getFullYear(), displayDate.getMonth(), day); dObj.setHours(0,0,0,0);
                                        const isSel = selectedDate && selectedDate.getTime() === dObj.getTime();
                                        const isTod = today.getTime() === dObj.getTime();
                                        return (
                                            <div key={day} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 34 }}>
                                                <button onClick={() => handleDateSelect(day)} style={{ width: 30, height: 30, borderRadius: '50%', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: isSel || isTod ? 700 : 400, color: isSel ? '#fff' : isTod ? '#4f46e5' : dObj.getDay()===0 ? '#ff3b30' : '#1c1c1e', background: isSel ? '#4f46e5' : 'transparent', position: 'relative' }}>
                                                    {day}{isTod && !isSel && <span style={{ position: 'absolute', bottom: 3, left: '50%', transform: 'translateX(-50%)', width: 3, height: 3, borderRadius: '50%', background: '#4f46e5' }} />}
                                                </button>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                            <div style={{ borderTop: '1px solid rgba(0,0,0,0.08)', background: '#f2f2f7', display: 'flex', padding: '8px 12px', gap: 8 }}>
                                <button onClick={() => { const t = new Date(); onChange(`${String(t.getDate()).padStart(2,'0')}/${String(t.getMonth()+1).padStart(2,'0')}/${t.getFullYear()}`); setIsOpen(false); }} style={{ flex: 1, padding: '7px 0', borderRadius: 10, border: 'none', background: 'rgba(79,70,229,0.08)', color: '#4f46e5', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>Hôm nay</button>
                                <button onClick={() => setIsOpen(false)} style={{ flex: 1, padding: '7px 0', borderRadius: 10, border: 'none', background: '#4f46e5', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>Xong</button>
                            </div>
                        </div>, document.body
                    )}
                </div>
            );
        };

        const PeriodDropdown = ({ period, setPeriod, isActive, onToggle }) => {
            const dropdownRef = useRef(null);
            useEffect(() => {
                const handleClickOutside = (e) => { if (dropdownRef.current && !dropdownRef.current.contains(e.target)) onToggle(null); };
                if (isActive) document.addEventListener("mousedown", handleClickOutside);
                return () => document.removeEventListener("mousedown", handleClickOutside);
            }, [isActive]);
            const label = period.type === 'custom' ? 'Tùy ý' : period.type === 'year' ? 'Cả năm' : period.type === 'quarter' ? `Quý ${period.value}` : `Tháng ${period.value}`;
            return (
                <div className="relative" ref={dropdownRef}>
                    <div className="label-text text-indigo-600">Kỳ báo cáo</div>
                    <button onClick={() => onToggle(isActive ? null : 'period')} className={`filter-control justify-between border-indigo-100 ${isActive ? 'active shadow-sm' : ''}`}>
                        <span className="flex items-center gap-2"><Icon name="calendar" size={10} className="text-indigo-400"/> {period.year} - {label}</span>
                        <Icon name="chevron-down" size={10} className={`transition-transform ${isActive ? 'rotate-180 text-indigo-600' : 'opacity-40'}`} />
                    </button>
                    {isActive && (
                        <div className="absolute top-full left-0 mt-2 w-80 bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.25)] border border-slate-200 z-[500] p-4 space-y-4">
                            <div><div className="label-text mb-2 text-indigo-500">Năm</div><div className="flex gap-2">{[2024, 2025, 2026].map(y => (<button key={y} onClick={() => setPeriod({...period, year: y})} className={`flex-1 py-1.5 rounded-xl font-black text-[10px] ${period.year === y ? 'bg-indigo-600 text-white shadow-lg' : 'bg-slate-50 text-slate-400 hover:bg-slate-100'}`}>{y}</button>))}</div></div>
                            <div className="grid grid-cols-2 gap-4">
                                <div><div className="label-text mb-2">Tháng</div><div className="grid grid-cols-3 gap-1">{[1,2,3,4,5,6,7,8,9,10,11,12].map(m => (<button key={m} onClick={() => {setPeriod({...period, type: 'month', value: m}); onToggle(null);}} className={`py-1.5 rounded-lg font-bold text-[10px] ${period.type==='month' && period.value===m ? 'bg-indigo-50 text-indigo-600 ring-1 ring-indigo-200' : 'hover:bg-slate-50 text-slate-500'}`}>{m}</button>))}</div></div>
                                <div className="space-y-3">
                                    <div><div className="label-text mb-2">Quý</div><div className="grid grid-cols-2 gap-1">{[1,2,3,4].map(q => (<button key={q} onClick={() => {setPeriod({...period, type: 'quarter', value: q}); onToggle(null);}} className={`py-1.5 rounded-lg font-bold text-[10px] ${period.type==='quarter' && period.value===q ? 'bg-indigo-50 text-indigo-600 ring-1 ring-indigo-200' : 'hover:bg-slate-50 text-slate-500'}`}>Q{q}</button>))}</div></div>
                                    <div><div className="label-text mb-2">Khác</div><div className="flex flex-col gap-1"><button onClick={() => {setPeriod({...period, type: 'year', value: 1}); onToggle(null);}} className={`py-1.5 rounded-lg font-bold text-[10px] text-left px-3 ${period.type==='year' ? 'bg-indigo-50 text-indigo-600 ring-1 ring-indigo-200' : 'hover:bg-slate-50 text-slate-500'}`}>Cả năm</button><button onClick={() => {setPeriod({...period, type: 'custom', value: 1}); onToggle(null);}} className={`py-1.5 rounded-lg font-bold text-[10px] text-left px-3 ${period.type==='custom' ? 'bg-indigo-50 text-indigo-600 ring-1 ring-indigo-200' : 'hover:bg-slate-50 text-slate-500'}`}>Tùy ý</button></div></div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            );
        };

        const PremiumDropdown = ({ label, items, selectedItems, onSelect, isActive, onToggle, align = "left" }) => {
            const dropdownRef = useRef(null);
            const [search, setSearch] = useState("");
            useEffect(() => {
                const handleClickOutside = (e) => { if (dropdownRef.current && !dropdownRef.current.contains(e.target)) onToggle(null); };
                if (isActive) document.addEventListener("mousedown", handleClickOutside);
                return () => document.removeEventListener("mousedown", handleClickOutside);
            }, [isActive]);
            const filtered = (items || []).filter(i => (i.name || '').toLowerCase().includes(search.toLowerCase()) || (i.id || '').toLowerCase().includes(search.toLowerCase()));
            return (
                <div className="relative" ref={dropdownRef}>
                    <div className="label-text">{label}</div>
                    <button onClick={(e) => { e.stopPropagation(); e.preventDefault(); onToggle(isActive ? null : label); }} className={`filter-control justify-between ${selectedItems.length > 0 ? 'active border-indigo-300' : ''}`} type="button">
                        <span className="truncate">{selectedItems.length > 0 ? `${selectedItems.length} mục` : 'Tất cả'}</span>
                        <Icon name="chevron-down" size={10} className={`transition-transform ${isActive ? 'rotate-180 text-indigo-600' : 'opacity-40'}`} />
                    </button>
                    {isActive && (
                        <div className={`absolute top-full mt-2 w-80 bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.25)] border border-slate-200 z-[500] flex flex-col max-h-[400px] ${align === 'right' ? 'right-0' : 'left-0'}`}>
                            <div className="p-3 border-b bg-slate-50/80 rounded-t-2xl"><div className="relative"><Icon name="search" size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><input autoFocus type="text" placeholder={`Tìm ${label.toLowerCase()}...`} value={search} onChange={e => setSearch(e.target.value)} className="w-full border border-slate-200 bg-white rounded-xl pl-9 pr-4 py-2 outline-none focus:ring-2 focus:ring-primary/20 text-[11px] font-medium shadow-inner" /></div></div>
                            <div className="flex-1 overflow-auto p-2 custom-scrollbar space-y-1">
                                {filtered.map(item => (
                                    <div key={item.id} onClick={(e) => { e.stopPropagation(); onSelect(item.id); }} className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all ${selectedItems.includes(item.id) ? 'bg-indigo-600 text-white shadow-lg' : 'hover:bg-slate-50 text-slate-600'}`}>
                                        <div className={`w-4 h-4 border-2 rounded shrink-0 flex items-center justify-center ${selectedItems.includes(item.id) ? 'bg-white border-white text-indigo-600' : 'border-slate-300'}`}>{selectedItems.includes(item.id) && <Icon name="check" size={10}/>}</div>
                                        <div className="flex items-center gap-2 truncate">
                                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-black font-mono shrink-0 border ${selectedItems.includes(item.id) ? 'bg-indigo-500/50 border-indigo-400 text-white' : 'bg-slate-100 border-slate-200 text-slate-500'}`}>{item.id}</span>
                                            <span className="text-[11px] font-bold truncate leading-none">{item.name}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <div className="p-3 border-t bg-slate-50 flex justify-between items-center rounded-b-2xl"><button onClick={(e) => { e.stopPropagation(); selectedItems.forEach(id => onSelect(id)); }} type="button" className="text-[9px] font-black text-slate-400 hover:text-red-500 uppercase tracking-widest">Bỏ chọn</button><button onClick={(e) => { e.stopPropagation(); onToggle(null); }} type="button" className="bg-indigo-600 text-white px-6 py-2 rounded-xl font-black text-[10px] shadow-lg hover:bg-indigo-700">XÁC NHẬN</button>
                            </div>
                        </div>
                    )}
                </div>
            );
        };

        const APP_VERSION = 'v1.0.0';
        const APP_NAME = 'iPOS Ledger Studio';
        const REPORT_TYPES = [
            { id: 'BC005', name: 'BẢNG CÂN ĐỐI KẾ TOÁN (TT200)' },
            { id: 'BC006', name: 'BẢNG CÂN ĐỐI PHÁT SINH' },
            { id: 'BC007', name: 'SỔ NHẬT KÝ CHUNG (S03a-DN)' },
            { id: 'BC008', name: 'SỔ CHI TIẾT TÀI KHOẢN' },
        ];

        const CDKT_INDICATORS = [
            { id: '100', name: 'A. TÀI SẢN NGẮN HẠN (100=110+120+130+140+150)', type: 'section' },
            { id: '110', name: 'I. Tiền và các khoản tương đương tiền', type: 'group' },
            { id: '111', name: '1. Tiền', type: 'item' },
            { id: '112', name: '2. Các khoản tương đương tiền', type: 'item' },
            { id: '120', name: 'II. Đầu tư tài chính ngắn hạn (120=121+122+123)', type: 'group' },
            { id: '121', name: '1. Chứng khoán kinh doanh', type: 'item' },
            { id: '122', name: '2. Dự phòng giảm giá chứng khoán kinh doanh (*) (2)', type: 'item' },
            { id: '123', name: '3. Đầu tư nắm giữ đến ngày đáo hạn', type: 'item' },
            { id: '130', name: 'III. Các khoản phải thu ngắn hạn', type: 'group' },
            { id: '131', name: '1. Phải thu ngắn hạn của khách hàng', type: 'item' },
            { id: '1311', name: '- Phải thu ngắn hạn (Quán ngoài)', type: 'sub' },
            { id: '1312', name: '- Phải thu ngắn hạn còn lại', type: 'sub' },
            { id: '132', name: '2. Trả trước cho người bán ngắn hạn', type: 'item' },
            { id: '133', name: '3. Phải thu nội bộ ngắn hạn', type: 'item' },
            { id: '134', name: '4. Phải thu theo tiến độ kế hoạch hợp đồng xây dựng', type: 'item' },
            { id: '135', name: '5. Phải thu về cho vay ngắn hạn', type: 'item' },
            { id: '136', name: '6. Phải thu ngắn hạn khác', type: 'item' },
            { id: '137', name: '7. Dự phòng phải thu ngắn hạn khó đòi (*)', type: 'item' },
            { id: '139', name: '8. Tài sản thiếu chờ xử lý', type: 'item' },
            { id: '140', name: 'IV. Hàng tồn kho', type: 'group' },
            { id: '141', name: '1. Hàng tồn kho', type: 'item' },
            { id: '149', name: '2. Dự phòng giảm giá tồn kho (*)', type: 'item' },
            { id: '150', name: 'V. Tài sản ngắn hạn khác', type: 'group' },
            { id: '151', name: '1. Chi phí trả trước ngắn hạn', type: 'item' },
            { id: '152', name: '2. Thuế GTGT được khấu trừ', type: 'item' },
            { id: '153', name: '3. Thuế và các khoản khác phải thu nhà nước', type: 'item' },
            { id: '154', name: '4. Giao dịch mua bán lại trái phiếu Chính phủ', type: 'item' },
            { id: '155', name: '5. Tài sản ngắn hạn khác', type: 'item' },
            { id: '200', name: 'B. TÀI SẢN DÀI HẠN (200=210+220+230+240)', type: 'section' },
            { id: '210', name: 'I. Các khoản phải thu dài hạn', type: 'group' },
            { id: '211', name: '1. Phải thu dài hạn của khách hàng', type: 'item' },
            { id: '212', name: '2. Trả trước cho người bán dài hạn', type: 'item' },
            { id: '213', name: '3. Vốn kinh doanh của đơn vị trực thuộc', type: 'item' },
            { id: '214', name: '4. Phải thu nội bộ dài hạn', type: 'item' },
            { id: '215', name: '5. Phải thu về cho vay dài hạn', type: 'item' },
            { id: '216', name: '6. Phải thu dài hạn khác', type: 'item' },
            { id: '217', name: '7. Dự phòng phải thu dài hạn khó đòi (*)', type: 'item' },
            { id: '220', name: 'II. Tài sản cố định', type: 'group' },
            { id: '221', name: '1. Tài sản cố định hữu hình', type: 'item' },
            { id: '222', name: ' - Nguyên giá', type: 'sub' },
            { id: '223', name: ' - Giá trị hao mòn lũy kế (*)', type: 'sub' },
            { id: '230', name: 'III. Bất động sản đầu tư', type: 'group' },
            { id: '231', name: '1. Nguyên giá', type: 'item' },
            { id: '232', name: '2. Giá trị hao mòn luỹ kế (*)', type: 'item' },
            { id: '240', name: 'IV. Tài sản dở dang dài hạn', type: 'group' },
            { id: '241', name: '1. Chi phí sản xuất, kinh doanh dở dang dài hạn', type: 'item' },
            { id: '242', name: '2. Chi phí xây dựng cơ bản dở dang', type: 'item' },
            { id: '250', name: 'V. Đầu tư tài chính dài hạn', type: 'group' },
            { id: '251', name: '1. Đầu tư vào công ty con', type: 'item' },
            { id: '252', name: '2. Đầu tư vào công ty liên doanh, liên kết', type: 'item' },
            { id: '260', name: 'VI. Tài sản dài hạn khác', type: 'group' },
            { id: '268', name: '4. Tài sản dài hạn khác', type: 'item' },
            { id: '270', name: 'TỔNG CỘNG TÀI SẢN  (270 = 100 + 200)', type: 'total' },
            { id: '300', name: 'C. NỢ PHẢI TRẢ (300 = 310 + 330)', type: 'section' },
            { id: '310', name: 'I. Nợ ngắn hạn', type: 'group' },
            { id: '311', name: '1. Phải trả người bán ngắn hạn', type: 'item' },
            { id: '312', name: '2. Người mua trả tiền trước ngắn hạn', type: 'item' },
            { id: '313', name: '3. Thuế và các khoản phải nộp NN', type: 'item' },
            { id: '314', name: '4. Phải trả người lao động', type: 'item' },
            { id: '315', name: '5. Chi phí phải trả ngắn hạn', type: 'item' },
            { id: '316', name: '6. Phải trả nội bộ ngắn hạn', type: 'item' },
            { id: '319', name: '9. Phải trả ngắn hạn khác', type: 'item' },
            { id: '324', name: '14. Giao dịch mua bán lại trái phiếu Chính phủ', type: 'item' },
            { id: '330', name: 'II. Nợ dài hạn', type: 'group' },
            { id: '331', name: '1. Phải trả người bán dài hạn', type: 'item' },
            { id: '332', name: '2. Người mua trả tiền trước dài hạn', type: 'item' },
            { id: '333', name: '3. Chi phí phải trả dài hạn', type: 'item' },
            { id: '334', name: '4. Phải trả nội bộ về vốn kinh doanh', type: 'item' },
            { id: '337', name: '7. Phải trả dài hạn khác', type: 'item' },
            { id: '338', name: '8. Vay và nợ thuê tài chính dài hạn', type: 'item' },
            { id: '340', name: '10. Cổ phiếu ưu đãi', type: 'item' },
            { id: '341', name: '11. Thuế thu nhập hoãn lại phải trả', type: 'item' },
            { id: '342', name: '12. Dự phòng phải trả dài hạn', type: 'item' },
            { id: '343', name: '13. Quỹ phát triển khoa học và công nghệ', type: 'item' },
            { id: '400', name: 'D. VỐN CHỦ SỞ HỮU (400 = 410 + 430)', type: 'section' },
            { id: '410', name: 'I. Vốn chủ sở hữu', type: 'group' },
            { id: '411', name: '1. Vốn góp của chủ sở hữu', type: 'item' },
            { id: '411A', name: ' - Cổ phiếu phổ thông có quyền biểu quyết', type: 'sub' },
            { id: '411B', name: ' - Cổ phiếu ưu đãi', type: 'sub' },
            { id: '412', name: '2. Thặng dư vốn cổ phần', type: 'item' },
            { id: '413', name: '3. Quyền chọn chuyển đổi trái phiếu', type: 'item' },
            { id: '414', name: '4. Vốn khác của chủ sở hữu', type: 'item' },
            { id: '415', name: '5. Cổ phiếu quỹ (*)', type: 'item' },
            { id: '416', name: '6. Chênh lệch đánh giá lại tài sản', type: 'item' },
            { id: '417', name: '7. Chênh lệch tỷ giá hối đoái', type: 'item' },
            { id: '418', name: '8. Quỹ đầu tư phát triển', type: 'item' },
            { id: '419', name: '9. Quỹ hỗ trợ sắp xếp doanh nghiệp', type: 'item' },
            { id: '420', name: '10. Quỹ khác thuộc vốn chủ sở hữu', type: 'item' },
            { id: '421', name: '11. Lợi nhuận sau thuế chưa phân phối', type: 'item' },
            { id: '421A', name: ' - Lợi nhuận sau thuế chưa phân phối đến cuối kỳ trước', type: 'sub' },
            { id: '421B', name: ' - Lợi nhuận chưa phân phối kỳ này', type: 'sub' },
            { id: '422', name: '12. Nguồn vốn đầu tư xây dựng cơ bản', type: 'item' },
            { id: '430', name: 'II. Nguồn kinh phí và quỹ khác', type: 'group' },
            { id: '431', name: '1. Nguồn kinh phí', type: 'item' },
            { id: '432', name: '2. Nguồn kinh phí đã hình thành tài sản cố định', type: 'item' },
            { id: '440', name: 'TỔNG CỘNG NGUỒN VỐN  (440 = 300 + 400)', type: 'total' },
        ];

        const ReportTypeDropdown = ({ value, onChange, isActive, onToggle }) => {
            const ref = useRef(null);
            useEffect(() => {
                const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) onToggle(null); };
                if (isActive) document.addEventListener('mousedown', handler);
                return () => document.removeEventListener('mousedown', handler);
            }, [isActive]);
            const current = REPORT_TYPES.find(r => r.id === value) || REPORT_TYPES[0];
            return (
                <div className="relative" ref={ref}>
                    <div className="label-text text-violet-600">Mẫu báo cáo</div>
                    <button onClick={() => onToggle(isActive ? null : 'reportType')} className={`filter-control justify-between border-violet-100 ${isActive ? 'active ring-2 ring-violet-100 border-violet-400 text-violet-700' : ''}`} style={{ width: 240 }}>
                        <span className="flex items-center gap-2 truncate">
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-black bg-violet-100 text-violet-600 border border-violet-200 shrink-0">{current.id}</span>
                            <span className="truncate text-[10px]">{current.name}</span>
                        </span>
                        <Icon name="chevron-down" size={10} className={`transition-transform shrink-0 ml-1 ${isActive ? 'rotate-180 text-violet-600' : 'opacity-40'}`} />
                    </button>
                    {isActive && (
                        <div className="absolute top-full right-0 mt-2 w-72 bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.25)] border border-slate-200 z-[500] overflow-hidden">
                            {REPORT_TYPES.map(rt => (
                                <div key={rt.id} onClick={() => { onChange(rt.id); onToggle(null); }}
                                    className={`flex items-center gap-3 px-4 py-3 cursor-pointer transition-all ${value === rt.id ? 'bg-violet-600 text-white' : 'hover:bg-slate-50 text-slate-700'}`}>
                                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-black border shrink-0 ${value === rt.id ? 'bg-violet-500/50 border-violet-400 text-white' : 'bg-slate-100 border-slate-200 text-slate-500'}`}>{rt.id}</span>
                                    <span className="text-[11px] font-bold">{rt.name}</span>
                                    {value === rt.id && <Icon name="check" size={12} className="ml-auto shrink-0" />}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            );
        };

        const ReportTab = ({ filters, period, setPeriod, meta, onToggleFilter, activeDropdown, setActiveDropdown, reportData: initialReportData, loadReportData, loading, monthList, monthlyData: initialMonthlyData, jobList, jobData: initialJobData, reportType, setReportType, setPendingReportType, setShowClearModal, trialBalanceData, trialBalanceTotal }) => {
            let indicators = [
                { id: '01', note: '', type: 'group', name: '1. DOANH THU BÁN HÀNG VÀ CUNG CẤP DỊCH VỤ' },
                { id: '011', note: '', type: 'sub', name: '- Tổng doanh thu - Cà phê' },
                { id: '012', note: '', type: 'sub', name: '- Tổng doanh thu - Trà / Thức uống khác / Túi' },
                { id: '013', note: '', type: 'sub', name: '- Tổng doanh thu - Food' },
                { id: '014', note: '', type: 'sub', name: '- Tổng doanh thu - Cheap Meal Dishes..' },
                { id: '015', note: '', type: 'sub', name: '- Tổng doanh thu - MERCHANDISE' },
                { id: '016', note: '', type: 'sub', name: '- Tổng doanh thu - Take Away' },
                { id: '017', note: '', type: 'sub', name: '- Tổng doanh thu - Món ngon đồng giá' },
                { id: '018', note: '', type: 'sub', name: '- Tổng doanh thu - Combo' },
                { id: '019', note: '', type: 'sub', name: '- Tổng doanh thu - Khác' },
                { id: '02', note: '', type: 'group', name: '2. CÁC KHOẢN GIẢM TRỪ DOANH THU' },
                { id: '020', note: '', type: 'sub', name: '2.1 Giảm giá' },
                { id: '03', note: '', type: 'group', name: '3. Doanh thu thuần về bán hàng và cung cấp dịch vụ' },
                { id: '04', note: '', type: 'group', name: '4. Giá vốn hàng bán' },
                { id: '05', note: '', type: 'group', name: '5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ' },
                { id: '06', note: '', type: 'group', name: '6. Doanh thu hoạt động tài chính' },
                { id: '061', note: '', type: 'sub', name: '- Doanh thu hoạt động tài chính' },
                { id: '07', note: '', type: 'group', name: '7. Chi phí tài chính' },
                { id: '071', note: '', type: 'sub', name: '- Trong đó: Chi phí lãi vay' },
                { id: '08', note: '', type: 'group', name: '8. Chi phí bán hàng + Chi quản lý doanh nghiệp' },
                { id: '081', note: '', type: 'sub', name: '* Chi phí thương hiệu & tiếp thị' },
                { id: '08101', note: 'THTT.BST', type: 'sub2', name: '- Chi phí quảng cáo Bộ sưu tập mới/Sự kiện cty' },
                { id: '08102', note: 'THTT.CFB', type: 'sub2', name: '- Chi phí chụp hình feedback' },
                { id: '08103', note: 'THTT.CLB', type: 'sub2', name: '- Chi phí chụp hình lookbook' },
                { id: '08104', note: 'THTT.CST', type: 'sub2', name: '- Chi phí chụp hình studio' },
                { id: '08105', note: 'THTT.PTK', type: 'sub2', name: '- Chi phí phát triển kênh/giao diện/nền tảng bán hàng' },
                { id: '08106', note: 'THTT.QST', type: 'sub2', name: '- Chi phí quay clip studio' },
                { id: '08107', note: 'THTT.SXM', type: 'sub2', name: '- Chi phí sản xuất media' },
                { id: '08108', note: 'THTT.INAN', type: 'sub2', name: '- Chi phí in ấn POSM' },
                { id: '08109', note: 'THTT.TKE', type: 'sub2', name: '- Chi phí thiết kế hình ảnh, ấn phẩm' },
                { id: '08110', note: 'THTT.KOL', type: 'sub2', name: '- Chi phí booking KOL/ KOC/ Celeb/ Báo chí' },
                { id: '08111', note: 'THTT.TCSK', type: 'sub2', name: '- Chi phí tổ chức sự kiện' },
                { id: '08112', note: 'THTT.TVTNT', type: 'sub2', name: '- Chi phí thuê vị trí hiển thị trên các nền tảng Digital' },
                { id: '08113', note: 'THTT.TBQC', type: 'sub2', name: '- Chi phí thuê bảng quảng cáo/ LED/ OOH/ DOOH' },
                { id: '08114', note: 'THTT.TN', type: 'sub2', name: '- Chi phí thiện nguyện/Charity Expenses' },
                { id: '082', note: '', type: 'sub', name: '* Chi phí Tiếp thị thương mại' },
                { id: '08201', note: 'TTTM.CBQT', type: 'sub2', name: '- Phí khuyến mãi combo linh hoạt - quà tặng' },
                { id: '08202', note: 'TTTM.QT', type: 'sub2', name: '- Chi phí quà tặng KOL/BOD/đối tác' },
                { id: '08203', note: 'TTTM.QTBH', type: 'sub2', name: '- Chi phí quà tặng bán hàng' },
                { id: '08204', note: 'TTTM.QTBST', type: 'sub2', name: '- Chi phí quà tặng Bộ sưu tập mới' },
                { id: '08205', note: 'TTTM.SPTD', type: 'sub2', name: '- Chi phí sản phẩm trao đổi/tài trợ' },
                { id: '083', note: '', type: 'sub', name: '* Chi phí Tiếp thị tăng trưởng' },
                { id: '08301', note: 'TTTT.GOI', type: 'sub2', name: '- Chi phí quảng cáo mua theo gói' },
                { id: '08302', note: 'TTTT.NS', type: 'sub2', name: '- Chi phí quảng cáo nội sàn' },
                { id: '08303', note: 'TTTT.QC', type: 'sub2', name: '- Chi phí quảng cáo trên kênh Social' },
                { id: '08304', note: 'TTTT.SMS', type: 'sub2', name: '- Chi phí gửi SMS bán hàng, CSKH' },
                { id: '08305', note: 'TTTT.ZALO', type: 'sub2', name: '- Chi phí gửi Zalo bán hàng, CSKH' },
                { id: '08306', note: 'TTTT.TTRI', type: 'sub2', name: '- Chi phí trang trí cửa hàng' },
                { id: '084', note: '', type: 'sub', name: '* Chi phí vận hành' },
                { id: '08401', note: 'VH.DTAC', type: 'sub2', name: '- Chi phí chiết khấu trả cho kênh đối tác' },
                { id: '08402', note: 'VH.PTDHT', type: 'sub2', name: '- Phí thúc đẩy hiển thị' },
                { id: '08403', note: 'VH.RENT', type: 'sub2', name: '- Phí thuê mặt bằng' },
                { id: '08404', note: 'VH.WATER', type: 'sub2', name: '- Phí nước' },
                { id: '08405', note: 'VH.ELETRIC', type: 'sub2', name: '- Phí điện' },
                { id: '08406', note: 'VH.PQL', type: 'sub2', name: '- Phí quản lý' },
                { id: '08407', note: 'VH.PQC', type: 'sub2', name: '- Phí quảng cáo' },
                { id: '08408', note: 'VH.INTERNET', type: 'sub2', name: '- Phí Internet' },
                { id: '084081', note: 'VH.PHH', type: 'sub2', name: '- Phí hoa hồng cho đối tác' },
                { id: '08409', note: 'VH.TELEPHONE', type: 'sub2', name: '- Phí điện thoại' },
                { id: '08410', note: 'VH.LBV', type: 'sub2', name: '- Chi phí lương- Bảo vệ' },
                { id: '08411', note: 'VH.PVC', type: 'sub2', name: '- Chi phí vận chuyển' },
                { id: '08412', note: 'VH.PRT', type: 'sub2', name: '- Phí rút tiền' },
                { id: '084121', note: 'VH.SCDP', type: 'sub2', name: '- Phí cọc thuê mặt bằng/ Security Deposit' },
                { id: '08413', note: 'VH.CPIN', type: 'sub2', name: '- Chi phí in ấn, photo' },
                { id: '085', note: '', type: 'sub', name: '* Chi phí Lương' },
                { id: '08501', note: 'TL.CPL', type: 'sub2', name: '- Chi phí lương' },
                { id: '08502', note: 'TL.KPI', type: 'sub2', name: '- Thưởng hiệu quả công việc (KPI)' },
                { id: '08503', note: 'TL.TDS', type: 'sub2', name: '- Chi phí thưởng doanh số' },
                { id: '08504', note: 'TL.CPL13', type: 'sub2', name: '- Lương tháng 13' },
                { id: '086', note: '', type: 'sub', name: '* Bảo hiểm và các chế độ liên quan' },
                { id: '08601', note: 'BHXH', type: 'sub2', name: '- Bảo hiểm xã hội' },
                { id: '08602', note: 'BHYT', type: 'sub2', name: '- Bảo hiểm y tế' },
                { id: '08603', note: 'KPCD', type: 'sub2', name: '- Kinh phí công đoàn' },
                { id: '08604', note: 'BHTNLD-BNN', type: 'sub2', name: '- Bảo hiểm tai nạn lao động, bệnh nghề nghiệp' },
                { id: '08605', note: 'BHTN', type: 'sub2', name: '- Bảo hiểm thất nghiệp' },
                { id: '087', note: '', type: 'sub', name: '* Thuế' },
                { id: '08701', note: 'TMB', type: 'sub2', name: '- Thuế- Môn bài' },
                { id: '08702', note: 'TGTGT', type: 'sub2', name: '- Thuế- GTGT' },
                { id: '08703', note: 'TPHAT', type: 'sub2', name: '- Thuế- Phạt' },
                { id: '08704', note: 'CPC.LPHI', type: 'sub2', name: '- Lệ phí / Administrative fees' },
                { id: '08705', note: 'CPC.TPHI', type: 'sub2', name: '- Phí, thuế phí' },
                { id: '088', note: '', type: 'sub', name: '* Chi phí khấu hao tài sản' },
                { id: '08801', note: 'KHTS', type: 'sub2', name: '- Khấu hao tài sản' },
                { id: '089', note: '', type: 'sub', name: '* Chi phí chung' },
                { id: '08901', note: 'CPC.BHGH', type: 'sub2', name: '- Phí bảo hiểm gian hàng' },
                { id: '08902', note: 'CPC.VPP', type: 'sub2', name: '- Phí văn phòng phẩm' },
                { id: '08903', note: 'CPC.BANK', type: 'sub2', name: '- Phí ngân hàng' },
                { id: '08904', note: 'CPC.PBTB', type: 'sub2', name: '- Phí phân bổ thiết bị' },
                { id: '08905', note: 'CPC.BAOTRI', type: 'sub2', name: '- Phí bảo trì, sửa chữa' },
                { id: '08906', note: 'CPC.CTAC', type: 'sub2', name: '- Phí đi công tác' },
                { id: '08907', note: 'CPC.CUNG', type: 'sub2', name: '- Phí mua đồ cúng' },
                { id: '08908', note: 'CPC.RAC', type: 'sub2', name: '- Tiền rác thải' },
                { id: '08909', note: 'CPC.NUOCU', type: 'sub2', name: '- Tiền nước uống' },
                { id: '08910', note: 'CPC.TK', type: 'sub2', name: '- Phí lót tay, bồi dưỡng' },
                { id: '08911', note: 'VH.XANG', type: 'sub2', name: '- Phí xăng' },
                { id: '08912', note: 'VH.BAIXE', type: 'sub2', name: '- Phí bãi xe' },
                { id: '08913', note: 'VH.ANUONG', type: 'sub2', name: '- Phí hỗ trợ ăn, uống cho nhân viên' },
                { id: '08914', note: 'VH.SIMDT', type: 'sub2', name: '- Phí sim điện thoại' },
                { id: '08915', note: 'CPC.SNNV', type: 'sub2', name: '- Phí sinh nhật nhân viên' },
                { id: '08916', note: 'CPC.BTRXE', type: 'sub2', name: '- Phí bảo trì xe' },
                { id: '08917', note: 'CPC.DCT', type: 'sub2', name: '- Phí diệt côn trùng' },
                { id: '08918', note: 'CPC.KHAC', type: 'sub2', name: '- Chi phí khác' },
                { id: '08919', note: 'VH.GAS', type: 'sub2', name: '- Phí gas' },
                { id: '08920', note: 'CPC.PNMEM', type: 'sub2', name: '- Phần mềm' },
                { id: '08921', note: 'CPC.DTD', type: 'sub2', name: '- Chi phí đăng tuyển dụng / Job advertising cost' },
                { id: '08922', note: '04001', type: 'sub2', name: '- Chi phí khác' },
                { id: '09', note: '', type: 'group', name: '9. Lợi nhuận thuần từ hoạt động kinh doanh' },
                { id: '10', note: '', type: 'group', name: '10. Thu nhập khác' },
                { id: '11', note: '', type: 'group', name: '11. Chi phí khác' },
                { id: '12', note: '', type: 'group', name: '12. Lợi nhuận khác' },
                { id: '13', note: '', type: 'group', name: '13. Tổng lợi nhuận kế toán trước thuế' },
                { id: '14', note: '', type: 'group', name: '14. Chi phí thuế TNDN hiện hành' },
                { id: '15', note: '', type: 'group', name: '15. Chi phí thuế TNDN hoãn lại' },
                { id: '16', note: '', type: 'group', name: '16. Lợi nhuận sau thuế TNDN' },
                { id: '17', note: '', type: 'group', name: '17. Lãi cơ bản trên cổ phiếu (*)' },
                { id: '18', note: '', type: 'group', name: '18. Lãi suy giảm trên cổ phiếu (*)' }
            ];

            let reportData = { ...initialReportData };
            let monthlyData = { ...initialMonthlyData };
            let jobData = { ...initialJobData };

            if (reportType === 'BC003' || reportType === 'BC004') {
                const idx020 = indicators.findIndex(r => r.id === '020');
                if (idx020 !== -1) {
                    indicators.splice(idx020 + 1, 0, { id: '084-VH.PHH', note: 'VH.PHH', type: 'sub', name: '2.2 Phí hoa hồng cho đối tác' });
                    indicators.splice(idx020 + 2, 0, { id: '084-VH.PQC', note: 'VH.PQC', type: 'sub', name: '2.3 Phí quảng cáo' });
                }
                
                const extractPhh = (dataObj, detailsKey) => {
                    let phhVal = 0;
                    if (dataObj[detailsKey]) {
                        const newDetails = [...dataObj[detailsKey]];
                        const pIdx = newDetails.findIndex(e => e.id === '084081' || e.id === 'VH.PHH' || (e.name && e.name.includes('VH.PHH')));
                        if (pIdx !== -1) {
                            phhVal = newDetails[pIdx].val;
                            newDetails.splice(pIdx, 1);
                            dataObj[detailsKey] = newDetails;
                        }
                    }
                    return phhVal;
                };

                const extractPqc = (dataObj, detailsKey) => {
                    let pqcVal = 0;
                    if (dataObj[detailsKey]) {
                        const newDetails = [...dataObj[detailsKey]];
                        const pIdx = newDetails.findIndex(e => e.id === '08407' || e.id === 'VH.PQC' || (e.name && e.name.includes('VH.PQC')));
                        if (pIdx !== -1) {
                            pqcVal = newDetails[pIdx].val;
                            newDetails.splice(pIdx, 1);
                            dataObj[detailsKey] = newDetails;
                        }
                    }
                    return pqcVal;
                };

                const processData = (dataObj) => {
                    const phh = extractPhh(dataObj, '_084_details');
                    const pqc = extractPqc(dataObj, '_084_details');
                    dataObj['084-VH.PHH'] = phh;
                    dataObj['084-VH.PQC'] = pqc;
                    dataObj['02'] = Number(dataObj['020'] || 0) + Number(phh) + Number(pqc);
                    dataObj['03'] = Number(dataObj['01'] || 0) - Number(dataObj['02'] || 0);
                    dataObj['05'] = Number(dataObj['03'] || 0) - Number(dataObj['04'] || 0);
                    dataObj['084'] = Number(dataObj['084'] || 0) - Number(phh) - Number(pqc);
                    dataObj['08'] = Number(dataObj['08'] || 0) - Number(phh) - Number(pqc);
                };

                processData(reportData);
                
                for (let key in monthlyData) {
                    let mData = { ...monthlyData[key] };
                    processData(mData);
                    monthlyData[key] = mData;
                }
                
                for (let key in jobData) {
                    let jData = { ...jobData[key] };
                    processData(jData);
                    jobData[key] = jData;
                }
            }

            const formatNum = (n) => {
                if (!n) return '-';
                const num = Number(n);
                if (num === 0) return '-';
                if (num < 0) return `(${Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })})`;
                return num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
            };
            const calcRate = (val, dataSet) => {
                const revenue = (dataSet || reportData)['01'] || 0;
                if (!revenue || !val) return '-';
                const num = (val / revenue) * 100;
                if (num < 0) return `(${Math.abs(num).toFixed(2)}%)`;
                return num.toFixed(2) + '%';
            };
            const monthNames = ['','Tháng 1','Tháng 2','Tháng 3','Tháng 4','Tháng 5','Tháng 6','Tháng 7','Tháng 8','Tháng 9','Tháng 10','Tháng 11','Tháng 12'];

            const exportToExcel = () => {
                const originalTable = document.querySelector(".report-table");
                if (!originalTable) return;
                
                const clonedTable = originalTable.cloneNode(true);
                
                // Chuẩn hóa dữ liệu số cho Excel
                clonedTable.querySelectorAll('td.col-value').forEach(td => {
                    let text = td.innerText.trim();
                    if (text === '') {
                        td.innerText = '';
                    } else if (text === '-') {
                        td.innerText = '0';
                    } else {
                        // Web đang dùng en-US nên phân cách hàng nghìn là dấu phẩy ","
                        const cleanVal = text.replace(/,/g, '');
                        td.innerText = cleanVal;
                    }
                    const currentStyle = td.getAttribute('style') || '';
                    td.setAttribute('style', currentStyle + 'mso-number-format:"\\#\\,\\#\\#0";');
                });

                clonedTable.querySelectorAll('td.col-rate').forEach(td => {
                    let text = td.innerText.trim();
                    if (text === '') {
                        td.innerText = '';
                    } else if (text === '-') {
                        td.innerText = '0';
                    } else if (text.endsWith('%')) {
                        const val = parseFloat(text.replace('%', '')) / 100;
                        td.innerText = val;
                    }
                    const currentStyle = td.getAttribute('style') || '';
                    td.setAttribute('style', currentStyle + 'mso-number-format:"0\\.00%";');
                });

                clonedTable.querySelectorAll('td.col-code').forEach(td => {
                    const currentStyle = td.getAttribute('style') || '';
                    td.setAttribute('style', currentStyle + 'mso-number-format:"\\@"; text-align: center;');
                });

                const tableHtml = clonedTable.outerHTML;
                const headerHtml = document.querySelector(".report-paper > div:first-child").outerHTML;
                const titleHtml = document.querySelector(".report-paper > div:nth-child(2)").outerHTML;
                
                const style = `<style>
                    table { border-collapse: collapse; width: 100%; font-family: 'Arial', sans-serif; }
                    th, td { border: 1px solid #000; padding: 5px; font-size: 10pt; }
                    th { background-color: #f1f5f9; font-weight: bold; text-align: center !important; }
                    td.col-value, td.col-rate { text-align: right; }
                    .row-group { font-weight: bold; background-color: #f8fafc; }
                    .row-sub { padding-left: 20px; }
                    .force-bold { font-weight: bold !important; }
                    .force-normal { font-weight: 400 !important; }
                </style>`;
                
                const template = `<html><head>

<meta charset="utf-8">${style}</head><body>${headerHtml}${titleHtml}${tableHtml}</body></html>`;
                const blob = new Blob([template], { type: "application/vnd.ms-excel" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = reportType === 'BC006'
                    ? `BC006_Bang_Can_Doi_Phat_Sinh_${period.year}_${period.value}.xls`
                    : reportType === 'BC005'
                    ? `BC005_Bang_Can_Doi_Ke_Toan_${period.year}_${period.value}.xls`
                    : reportType === 'BC007'
                    ? `BC007_So_Nhat_Ky_Chung_${period.year}_${period.value}.xls`
                    : `BC008_So_Chi_Tiet_Tai_Khoan_${period.year}_${period.value}.xls`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                setTimeout(() => URL.revokeObjectURL(url), 1000);
            };
            const exportToPDF = () => { window.print(); };

            return (
                <div className="flex-1 overflow-hidden flex flex-col">
                    <div className="bg-white border-b border-slate-200 p-3 px-6 shrink-0 shadow-sm z-[900] space-y-3">
                        <div className="flex items-end gap-3">
                            <div className="w-60"><PeriodDropdown period={period} setPeriod={setPeriod} isActive={activeDropdown === 'period'} onToggle={setActiveDropdown} /></div>
                            <div className="w-32">
                                <IOSDatePicker label="Từ ngày" value={filters.from_date} onChange={val => onToggleFilter('from_date', val)} disabled={period.type !== 'custom'} />
                            </div>
                            <div className="w-32">
                                <IOSDatePicker label="Đến ngày" value={filters.to_date} onChange={val => onToggleFilter('to_date', val)} disabled={period.type !== 'custom'} />
                            </div>
                            <div className="w-40"><PremiumDropdown label="Đơn vị" items={meta.orgs} selectedItems={filters.org_ids} onSelect={id => onToggleFilter('org_ids', id)} isActive={activeDropdown === 'Đơn vị'} onToggle={setActiveDropdown} /></div>
                            {reportType === 'BC008' ? (
                                <div className="w-40"><PremiumDropdown label="Tài khoản" items={meta.accounts} selectedItems={filters.acc_ids} onSelect={id => onToggleFilter('acc_ids', id)} isActive={activeDropdown === 'Tài khoản'} onToggle={setActiveDropdown} /></div>
                            ) : null}
                            <div className="ml-auto"><ReportTypeDropdown value={reportType} onChange={(type) => { if (type !== reportType && Object.keys(reportData).length > 0) { setPendingReportType(type); setShowClearModal(true); } else { setReportType(type); } }} isActive={activeDropdown === 'reportType'} onToggle={setActiveDropdown} /></div>
                            <div className="flex gap-1.5">
                                <button onClick={loadReportData} disabled={loading} className="bg-indigo-600 text-white px-5 h-[32px] rounded-lg font-black text-[9px] shadow-lg hover:bg-indigo-700 transition-all uppercase tracking-widest flex items-center gap-2">
                                    {loading && <Icon name="loader" className="animate-spin" />}
                                    Xem {reportType}
                                </button>
                                <button onClick={exportToExcel} disabled={reportType === 'BC006' ? trialBalanceData.length === 0 : Object.keys(reportData).length === 0} className="bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 h-[32px] rounded-lg font-black text-[9px] shadow-lg hover:bg-emerald-700 hover:disabled:bg-emerald-600 transition-all flex items-center gap-2"><Icon name="file-spreadsheet" size={12}/> EXCEL</button>
                                <button onClick={exportToPDF} disabled={reportType === 'BC006' ? trialBalanceData.length === 0 : Object.keys(reportData).length === 0} className="bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 h-[32px] rounded-lg font-black text-[9px] shadow-lg hover:bg-red-700 hover:disabled:bg-red-600 transition-all flex items-center gap-2"><Icon name="download" size={12}/> PDF</button>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 overflow-auto custom-scrollbar bg-slate-300/40 p-4">
                        <div className="report-paper">
                            <div className="flex justify-between items-start mb-6">
                                <div>
                                    <div className="font-black text-[11px] uppercase">CÔNG TY TNHH DUONG THANH LONG</div>
                                    <div className="font-bold text-[9px] text-slate-500 uppercase mt-0.5">
                                        {filters.org_ids.length > 0 ? (
                                            meta.orgs.find(o => o.id === filters.org_ids[0])?.name || 'Đơn vị: ' + filters.org_ids[0]
                                        ) : 'Tất cả đơn vị'}
                                    </div>
                                    <div className="text-[9px] text-slate-400 italic">
                                        {filters.org_ids.length > 0 ? (
                                            meta.orgs.find(o => o.id === filters.org_ids[0])?.address || '...'
                                        ) : ''}
                                    </div>
                                </div>
                                <div className="text-right font-black text-[10px] text-slate-400 uppercase tracking-widest italic underline">{reportType === 'BC005' ? 'Mẫu B01 - DN' : 'Mẫu B02 - DN'}</div>
                            </div>

                            <div className="text-center space-y-1 mb-8">
                                <h1 className="text-xl font-black text-slate-900 uppercase tracking-tight">{reportType === 'BC006' ? 'BẢNG CÂN ĐỐI PHÁT SINH' : reportType === 'BC005' ? 'BẢNG CÂN ĐỐI KẾ TOÁN' : ['BC002', 'BC004'].includes(reportType) ? 'BÁO CÁO KẾT QUẢ KINH DOANH THEO CÔNG VIỆC' : 'BÁO CÁO KẾT QUẢ KINH DOANH THEO THÁNG'}</h1>
                                <div className="text-[10px] font-bold text-slate-600 uppercase">Đơn vị: {filters.org_ids.length > 0 ? filters.org_ids.map(id => {
                                    const org = meta.orgs.find(o => o.id === id);
                                    return org ? `${id} - ${org.name}` : id;
                                }).join(', ') : 'Tất cả'}</div>
                                <div className="text-[11px] font-black text-indigo-700 uppercase">{
                                    period.type === 'month' ? `Tháng ${period.value} Năm ${period.year}` :
                                    period.type === 'quarter' ? `Quý ${period.value} Năm ${period.year}` :
                                    period.type === 'year' ? `Năm ${period.year}` :
                                    `Từ ngày ${filters.from_date} Đến ngày ${filters.to_date}`
                                }</div>
                                <div className="text-[9px] text-slate-500 italic">Đơn vị tính: VND</div>
                            </div>

                            <div className="overflow-x-auto">
                                {reportType === 'BC006' && (
                                    <style>{`
                                        .bc006-table .col-name { width: 220px !important; min-width: 220px !important; white-space: normal; font-size: 11px; }
                                        .bc006-table .col-value { width: 105px !important; min-width: 105px !important; padding: 4px !important; font-size: 11px; }
                                        .bc006-table .col-code { width: 60px !important; min-width: 60px !important; font-size: 11px; }
                                        .bc006-table th { font-size: 10px !important; padding: 4px !important; }
                                    `}</style>
                                )}
                                <table className={`report-table min-w-full ${reportType === 'BC006' ? 'bc006-table' : ''}`}>
                                    {reportType === 'BC006' ? (
                                        <>
                                        <thead>
                                            <tr>
                                                <th rowSpan="2" className="col-code border border-slate-300">Mã tài khoản</th>
                                                <th rowSpan="2" className="col-name border border-slate-300">Tên tài khoản</th>
                                                <th colSpan="2" className="text-center border border-slate-300">Dư đầu kỳ</th>
                                                <th colSpan="2" className="text-center border border-slate-300">Phát sinh trong kỳ</th>
                                                <th colSpan="2" className="text-center border border-slate-300">Dư cuối kỳ</th>
                                            </tr>
                                            <tr>
                                                <th className="col-value border border-slate-300 text-center">Nợ</th>
                                                <th className="col-value border border-slate-300 text-center">Có</th>
                                                <th className="col-value border border-slate-300 text-center">Nợ</th>
                                                <th className="col-value border border-slate-300 text-center">Có</th>
                                                <th className="col-value border border-slate-300 text-center">Nợ</th>
                                                <th className="col-value border border-slate-300 text-center">Có</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {trialBalanceData.map((row, idx) => {
                                                const isBold = row.is_parent || row.id.length <= 3;
                                                const fw = isBold ? 800 : 400;
                                                return (
                                                    <tr key={idx} className={isBold ? 'bg-slate-50' : ''}>
                                                        <td className="col-code" style={{ fontWeight: fw }}>{row.id}</td>
                                                        <td className={`row-name col-name${row.id.length > 3 ? ' row-sub' : ''}`} style={{ fontWeight: fw }}>{row.name}</td>
                                                        <td className="col-value" style={{ fontWeight: fw }}>{formatNum(row.open_deb)}</td>
                                                        <td className="col-value" style={{ fontWeight: fw }}>{formatNum(row.open_crd)}</td>
                                                        <td className="col-value" style={{ fontWeight: fw }}>{formatNum(row.period_deb)}</td>
                                                        <td className="col-value" style={{ fontWeight: fw }}>{formatNum(row.period_crd)}</td>
                                                        <td className="col-value" style={{ fontWeight: fw }}>{formatNum(row.close_deb)}</td>
                                                        <td className="col-value" style={{ fontWeight: fw }}>{formatNum(row.close_crd)}</td>
                                                    </tr>
                                                );
                                            })}
                                            {trialBalanceTotal && (
                                                <tr className="row-group text-indigo-900 border-t-2 border-indigo-200">
                                                    <td colSpan="2" className="text-right py-3 px-4 font-black uppercase tracking-widest text-xs">Tổng cộng</td>
                                                    <td className="col-value font-black">{formatNum(trialBalanceTotal.open_deb)}</td>
                                                    <td className="col-value font-black">{formatNum(trialBalanceTotal.open_crd)}</td>
                                                    <td className="col-value font-black">{formatNum(trialBalanceTotal.period_deb)}</td>
                                                    <td className="col-value font-black">{formatNum(trialBalanceTotal.period_crd)}</td>
                                                    <td className="col-value font-black">{formatNum(trialBalanceTotal.close_deb)}</td>
                                                    <td className="col-value font-black">{formatNum(trialBalanceTotal.close_crd)}</td>
                                                </tr>
                                            )}
                                        </tbody>
                                        </>
                                    ) : reportType === 'BC005' ? (
                                        <>
                                        <thead>
                                            <tr>
                                                <th rowSpan="2" className="col-name">Chỉ tiêu</th>
                                                <th rowSpan="2" className="col-code">Mã số</th>
                                                <th className="col-value">Kỳ này</th>
                                                <th className="col-value">Kỳ trước</th>
                                            </tr>
                                            <tr></tr>
                                        </thead>
                                        <tbody>
                                            {CDKT_INDICATORS.map((row, idx) => {
                                                const closing = (reportData.closing || {})[row.id] || 0;
                                                const opening = (reportData.opening || {})[row.id] || 0;
                                                const isSection = row.type === 'section' || row.type === 'total';
                                                const isGroup = row.type === 'group';
                                                const isSub = row.type === 'sub';
                                                const isBold = isSection || isGroup || row.type === 'total';
                                                const indent = isSub ? ' row-sub2' : (row.type === 'item' ? ' row-sub' : '');
                                                return (
                                                    <tr key={idx} className={isSection ? 'row-group' : (isGroup ? 'row-group' : '')}>
                                                        <td className={`row-name col-name${indent}`} style={{ fontWeight: isBold ? 800 : 300 }}>{row.name}</td>
                                                        <td className="col-code" style={{ fontWeight: isBold ? 800 : 300 }}>{row.id}</td>
                                                        <td className="col-value" style={{ fontWeight: isBold ? 800 : 300 }}>{formatNum(closing)}</td>
                                                        <td className="col-value" style={{ fontWeight: isBold ? 800 : 300 }}>{row.id === '421A' ? '' : formatNum(opening)}</td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                        </>
                                    ) : ['BC001', 'BC003'].includes(reportType) ? (
                                        <>
                                        <thead>
                                            <tr>
                                                <th rowSpan="2" className="col-code">Mã số</th>
                                                <th rowSpan="2" className="col-name">Chỉ tiêu</th>
                                                <th colSpan="2">Tổng phát sinh</th>
                                                {monthList.map((m, i) => (
                                                    <th key={i} colSpan="2">{monthNames[m.month]} - {m.year}</th>
                                                ))}
                                            </tr>
                                            <tr>
                                                <th className="col-value">Giá trị</th>
                                                <th className="col-rate">Tỷ lệ %</th>
                                                {monthList.map((m, i) => (
                                                    <React.Fragment key={i}>
                                                        <th className="col-value">Giá trị</th>
                                                        <th className="col-rate">Tỷ lệ %</th>
                                                    </React.Fragment>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {indicators.map((row, idx) => {
                                                if (row.id !== '084-VH.PHH' && row.id !== '084-VH.PQC' && row.id >= '08101' && row.id <= '08922' && row.id !== '082' && row.id !== '083' && row.id !== '084' && row.id !== '085' && row.id !== '086' && row.id !== '087' && row.id !== '088' && row.id !== '089') return null;
                                                const val = reportData[row.id] || 0;
                                                
                                                let isRowAllZero = (Number(val) === 0);
                                                if (isRowAllZero) {
                                                    for (let m of monthList) {
                                                        const mKey = `${m.month}_${m.year}`;
                                                        const mData = monthlyData[mKey] || {};
                                                        if (Number(mData[row.id] || 0) !== 0) { isRowAllZero = false; break; }
                                                    }
                                                }
                                                if (isRowAllZero) return null;
                                                
                                                const isBold = (row.id === '011') ? false : (row.type === 'group' || (row.name && row.name.trim().startsWith('*')));
                                                const mainRow = (
                                                    <tr key={idx} className={isBold ? 'row-group' : ''}>
                                                        <td className="col-code" style={{ fontWeight: isBold ? 800 : 300 }}>{row.id === '084-VH.PHH' ? 'VH.PHH' : row.id === '084-VH.PQC' ? 'VH.PQC' : row.id}</td>
                                                        <td className={`row-name col-name ${row.type === 'sub' ? 'row-sub' : row.type === 'sub2' ? 'row-sub2' : ''}`} style={{ fontWeight: isBold ? 800 : 300 }}>{row.name}</td>
                                                        <td className="col-value" style={{ fontWeight: isBold ? 800 : 300 }}>{formatNum(val)}</td>
                                                        <td className="col-rate" style={{ fontWeight: isBold ? 800 : 300 }}>{calcRate(val, reportData)}</td>
                                                        {monthList.map((m, i) => {
                                                            const mKey = `${m.month}_${m.year}`;
                                                            const mData = monthlyData[mKey] || {};
                                                            const mVal = mData[row.id] || 0;
                                                            return (
                                                                <React.Fragment key={i}>
                                                                    <td className="col-value" style={{ fontWeight: isBold ? 800 : 300 }}>{formatNum(mVal)}</td>
                                                                    <td className="col-rate" style={{ fontWeight: isBold ? 800 : 300 }}>{calcRate(mVal, mData)}</td>
                                                                </React.Fragment>
                                                            );
                                                        })}
                                                    </tr>
                                                );
                                                const detailsKey = `_${row.id}_details`;
                                                if (['081','082','083','084','085','086','087','088','089'].includes(row.id)) {
                                                    const details = reportData[detailsKey] || [];
                                                    const detailRows = details.map((exp, i) => {
                                                        let isDetailAllZero = (Number(exp.val) === 0);
                                                        if (isDetailAllZero) {
                                                            for (let m of monthList) {
                                                                const mKey = `${m.month}_${m.year}`;
                                                                const mMonthData = monthlyData[mKey] || {};
                                                                const mDetails = mMonthData[detailsKey] || [];
                                                                const mExp = mDetails.find(e => e.id === exp.id);
                                                                if (mExp && Number(mExp.val) !== 0) { isDetailAllZero = false; break; }
                                                            }
                                                        }
                                                        if (isDetailAllZero) return null;
                                                        return (
                                                        <tr key={`${row.id}_${i}`}>
                                                            <td className="col-code force-normal">{exp.id}</td>
                                                            <td className="row-name col-name row-sub2 force-normal">{exp.name ? exp.name.split('/')[0].trim() : ''}</td>
                                                            <td className="col-value force-normal">{formatNum(exp.val)}</td>
                                                            <td className="col-rate force-normal">{calcRate(exp.val, reportData)}</td>
                                                            {monthList.map((m, mi) => {
                                                                const mKey = `${m.month}_${m.year}`;
                                                                const mMonthData = monthlyData[mKey] || {};
                                                                const mDetails = mMonthData[detailsKey] || [];
                                                                const mExp = mDetails.find(e => e.id === exp.id);
                                                                const mVal = mExp ? mExp.val : 0;
                                                                return (
                                                                    <React.Fragment key={mi}>
                                                                        <td className="col-value force-normal">{formatNum(mVal)}</td>
                                                                        <td className="col-rate force-normal">{calcRate(mVal, mMonthData)}</td>
                                                                    </React.Fragment>
                                                                );
                                                            })}
                                                        </tr>
                                                        );
                                                    });
                                                    return <React.Fragment key={idx}>{mainRow}{detailRows}</React.Fragment>;
                                                }
                                                return mainRow;
                                            })}
                                        </tbody>
                                        </>
                                    ) : reportType === 'BC007' ? (
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
                                </table>
                            </div>

                            <div className="mt-12">
                                <div className="grid grid-cols-3 gap-10 text-center">
                                    <div></div>
                                    <div></div>
                                    <div className="text-[10px] italic text-slate-400 mb-2">TP. HCM, Ngày {new Date().getDate()} Tháng {new Date().getMonth() + 1} Năm {new Date().getFullYear()}</div>
                                </div>
                                <div className="grid grid-cols-3 gap-10 text-center items-start">
                                    <div><div className="font-black uppercase text-[10.5px]">Người lập biểu</div><div className="mt-20 italic text-slate-300 text-[9px]">(Ký, họ tên)</div></div>
                                    <div><div className="font-black uppercase text-[10.5px]">Kế toán trưởng</div><div className="mt-20 italic text-slate-300 text-[9px]">(Ký, họ tên)</div></div>
                                    <div><div className="font-black uppercase text-[10.5px]">Giám đốc</div><div className="mt-20 italic text-slate-300 text-[9px]">(Ký, họ tên)</div></div>
                                </div>
                            </div>
                            <div className="mt-16 text-[8px] text-slate-200 text-right italic tracking-widest uppercase border-t border-slate-50 pt-4">Page {period.value}/{period.year}</div>
                        </div>
                    </div>
                </div>
            );
        };

        // Header cột có thể sort. Click 1 lần: DESC. Click 2: ASC. Click 3: bỏ sort về default.
        const SortableHeader = ({ field, sort, onSort, className = '', children, align = 'center' }) => {
            const active = sort.field === field;
            const dir = active ? sort.dir : null;
            const justify = align === 'right' ? 'justify-end' : align === 'left' ? 'justify-start' : 'justify-center';
            return (
                <th
                    className={`sortable-th ${className} ${active ? 'is-sorted' : ''} cursor-move`}
                    onClick={() => onSort(field)}
                    title="Bấm để sắp xếp / Nắm kéo thả để gom nhóm"
                    draggable
                    onDragStart={e => e.dataTransfer.setData('text/plain', field)}
                >
                    <div className={`flex items-center gap-1 ${justify}`}>
                        <span>{children}</span>
                        <span className="sort-icon inline-flex">
                            {dir === 'asc'  ? <Icon name="arrow-up"     size={10}/>
                             : dir === 'desc' ? <Icon name="arrow-down"   size={10}/>
                             : <Icon name="arrows-updown" size={10}/>}
                        </span>
                    </div>
                </th>
            );
        };

        // Row component memo — chỉ re-render khi data của row đó thay đổi
        const PurchaseRow = memo(({ r, idx }) => (
            <tr className="hover:bg-indigo-50 border-b border-slate-50">
                <td className="border-r text-center">{idx}</td>
                <td className="border-r text-center italic">{r.ORGANIZATION_ID}</td>
                <td className="border-r whitespace-nowrap px-3 font-bold">{r.ORGANIZATION_NAME}</td>
                <td className="border-r text-center italic">{r.TRAN_ID}</td>
                <td className="border-r whitespace-nowrap px-3 italic">{r.TRAN_NAME}</td>
                <td className="border-r font-black px-3">{r.TRAN_NO}</td>
                <td className="border-r text-center font-bold">{r.TRAN_DATE}</td>
                <td className="border-r px-2 whitespace-nowrap">{r.VAT_TRAN_NO}</td>
                <td className="border-r text-center">{r.VAT_TRAN_DATE}</td>
                <td className="border-r text-center">{r.PO_TRAN_NO}</td>
                <td className="border-r text-center italic">{r.WAREHOUSE_ID}</td>
                <td className="border-r whitespace-nowrap px-3">{r.WAREHOUSE_NAME}</td>
                <td className="border-r text-center font-black text-indigo-600">{r.ITEM_ID}</td>
                <td className="border-r whitespace-nowrap px-3">{r.DESCRIPTION}</td>
                <td className="border-r text-center">{r.UNIT_ID}</td>
                <td className="border-r text-right font-mono px-2">{fmtNum(r.QUANTITY)}</td>
                <td className="border-r text-center">{r.UNIT_ID_WH}</td>
                <td className="border-r text-right font-mono px-2">{fmtNum(r.QUANTITY_WH)}</td>
                <td className="border-r text-right font-mono px-2">{fmtNum(r.UNIT_PRICE)}</td>
                <td className="border-r text-right font-mono px-2 text-orange-600">{fmtInt(r.DISCOUNT_AMOUNT)}</td>
                <td className="border-r text-right font-mono px-2">{fmtNum(r.PURCHASE_COST)}</td>
                <td className="border-r text-center">{r.VAT_TAX_RATE != null && r.VAT_TAX_RATE !== '' ? r.VAT_TAX_RATE + '%' : ''}</td>
                <td className="border-r text-right font-mono px-2 text-violet-600">{fmtInt(r.VAT_TAX_AMOUNT)}</td>
                <td className="border-r text-right font-mono font-black px-2 text-emerald-600">{fmtInt(r.TOTAL_AMOUNT)}</td>
                <td className="border-r text-center italic">{r.ACCOUNT_ID_COST}</td>
                <td className="border-r text-center italic">{r.PR_DETAIL_ID}</td>
                <td className="border-r whitespace-nowrap px-3 italic">{r.PR_DETAIL_NAME}</td>
                <td className="border-r text-center italic">{r.EXPENSE_ID}</td>
                <td className="border-r whitespace-nowrap px-3 italic">{r.EXPENSE_NAME}</td>
                <td className="border-r text-center italic">{r.JOB_ID}</td>
                <td className="whitespace-nowrap px-3 italic">{r.JOB_NAME}</td>
            </tr>
        ));

        const WarehouseRow = memo(({ r, idx }) => {
            const ir = r.ISSUE_RECEIVE;
            return (
                <tr className="hover:bg-indigo-50 border-b border-slate-50">
                    <td className="border-r text-center">{idx}</td>
                    <td className={`border-r text-center font-black ${ir==='N' ? 'text-emerald-600' : ir==='X' ? 'text-red-600' : ''}`}>{ir}</td>
                    <td className="border-r text-center italic">{r.ORGANIZATION_ID}</td>
                    <td className="border-r whitespace-nowrap px-3 font-bold">{r.ORGANIZATION_NAME}</td>
                    <td className="border-r text-center italic">{r.TRAN_ID}</td>
                    <td className="border-r whitespace-nowrap px-3 italic">{r.TRAN_NAME}</td>
                    <td className="border-r font-black px-3">{r.TRAN_NO}</td>
                    <td className="border-r text-center font-bold">{r.TRAN_DATE}</td>
                    <td className="border-r text-center italic">{r.WAREHOUSE_ID}</td>
                    <td className="border-r whitespace-nowrap px-3">{r.WAREHOUSE_NAME}</td>
                    <td className="border-r text-center italic">{r.WAREHOUSE_ID_ISSUE}</td>
                    <td className="border-r whitespace-nowrap px-3">{r.WAREHOUSE_NAME_ISSUE}</td>
                    <td className="border-r text-center font-black text-indigo-600">{r.ITEM_ID}</td>
                    <td className="border-r whitespace-nowrap px-3">{r.ITEM_NAME}</td>
                    <td className="border-r text-center">{r.UNIT_ID_WH}</td>
                    <td className="border-r text-right font-mono px-2">{fmtNum(r.QUANTITY)}</td>
                    <td className="border-r text-center">{r.UNIT_ID_EXTRA}</td>
                    <td className="border-r text-right font-mono px-2">{fmtNum(r.QUANTITY_EXTRA)}</td>
                    <td className="border-r text-right font-mono px-2">{fmtNum(r.UNIT_PRICE)}</td>
                    <td className="border-r text-right font-mono font-black px-2 text-emerald-600">{fmtInt(r.AMOUNT)}</td>
                    <td className="border-r text-center font-black text-indigo-600">{r.ACCOUNT_ID}</td>
                    <td className="border-r text-center italic">{r.ACCOUNT_ID_CONTRA}</td>
                    <td className="border-r text-center italic">{r.PR_DETAIL_ID}</td>
                    <td className="border-r whitespace-nowrap px-3 italic">{r.PR_DETAIL_NAME}</td>
                    <td className="border-r text-center italic">{r.EXPENSE_ID}</td>
                    <td className="border-r whitespace-nowrap px-3 italic">{r.EXPENSE_NAME}</td>
                    <td className="border-r text-center italic">{r.JOB_ID}</td>
                    <td className="whitespace-nowrap px-3 italic">{r.JOB_NAME}</td>
                </tr>
            );
        });

        const LedgerRow = memo(({ r, idx, pageSize }) => (
            <tr className="hover:bg-indigo-50 border-b border-slate-50">
                <td className="border-r text-center">{idx}</td>
                <td className="border-r text-center font-bold">{r.TRAN_DATE}</td>
                <td className="border-r font-black px-3">{r.TRAN_NO}</td>
                <td className="border-r text-center italic">{r.TRAN_ID}</td>
                <td className="border-r whitespace-nowrap px-3 italic">{r.TRAN_NAME}</td>
                <td className="border-r text-center font-black text-indigo-600">{r.ACCOUNT_ID}</td>
                <td className="border-r text-center">{r.ACCOUNT_ID_CONTRA}</td>
                <td className="border-r whitespace-nowrap px-3">{r.DESCRIPTION || r.COMMENTS}</td>
                <td className="border-r text-right font-mono font-black text-emerald-600 px-4">{r.DEBIT_CREDIT==='DEB' ? fmtNum(r.AMOUNT) : ''}</td>
                <td className="border-r text-right font-mono font-black text-red-600 px-4">{r.DEBIT_CREDIT==='CRD' ? fmtNum(r.AMOUNT) : ''}</td>
                <td className="border-r text-center italic">{r.PR_DETAIL_ID}</td>
                <td className="border-r whitespace-nowrap italic px-3">{r.PR_DETAIL_NAME}</td>
                <td className="border-r text-center font-bold text-teal-700">{r.PR_DETAIL_ID_CONTRA}</td>
                <td className="border-r whitespace-nowrap italic px-3 text-teal-700">{r.PR_DETAIL_NAME_CONTRA}</td>
                <td className="border-r text-center italic">{r.EXPENSE_ID}</td>
                <td className="border-r whitespace-nowrap italic px-4">{r.EXPENSE_NAME}</td>
                <td className="border-r text-center font-bold text-teal-700">{r.EXPENSE_ID_CONTRA}</td>
                <td className="border-r whitespace-nowrap italic px-4 text-teal-700">{r.EXPENSE_NAME_CONTRA}</td>
                <td className="border-r text-center italic">{r.ORGANIZATION_ID}</td>
                <td className="border-r whitespace-nowrap px-4 font-bold">{r.ORGANIZATION_NAME}</td>
                <td className="border-r text-center italic">{r.ITEM_ID}</td>
                <td className="border-r px-4 whitespace-nowrap italic">{r.ITEM_NAME}</td>
                <td className="border-r text-center font-bold text-teal-700">{r.ITEM_ID_CONTRA}</td>
                <td className="border-r px-4 whitespace-nowrap italic text-teal-700">{r.ITEM_NAME_CONTRA}</td>
                <td className="border-r text-center italic">{r.JOB_ID}</td>
                <td className="border-r px-4 whitespace-nowrap italic">{r.JOB_NAME}</td>
                <td className="border-r text-center font-bold text-teal-700">{r.JOB_ID_CONTRA}</td>
                <td className="border-r px-4 whitespace-nowrap italic text-teal-700">{r.JOB_NAME_CONTRA}</td>
                <td className="border-r text-center italic">{r.PRODUCT_ID}</td>
                <td className="border-r px-4 whitespace-nowrap italic">{r.PRODUCT_NAME}</td>
                <td className="border-r text-center font-bold text-indigo-700">{r.BANK_ID}</td>
                <td className="border-r px-4 whitespace-nowrap italic text-indigo-700">{r.BANK_NAME}</td>
                <td className="border-r text-center font-bold text-teal-700">{r.BANK_ID_CONTRA}</td>
                <td className="px-4 whitespace-nowrap italic text-teal-700">{r.BANK_NAME_CONTRA}</td>
            </tr>
        ));

        const FilterToggleButton = ({ expanded, onToggle, count = 0 }) => {
            return (
                <button type="button" onClick={onToggle}
                        title={expanded ? 'Thu gọn bộ lọc nâng cao' : 'Mở rộng bộ lọc nâng cao'}
                        className={`relative h-[40px] px-3 rounded-xl font-black text-[10px] uppercase tracking-wider transition-all active:scale-[0.98] flex items-center gap-1.5 shrink-0 border ${expanded ? 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-indigo-200 hover:text-indigo-600'}`}>
                    <Icon name="sliders" size={12}/>
                    <span>{expanded ? 'Thu gọn' : 'Bộ lọc'}</span>
                    {count > 0 && <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-[16px] px-1 rounded-full bg-indigo-600 text-white text-[8px] font-black flex items-center justify-center shadow">{count}</span>}
                    <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={9}/>
                </button>
            );
        };

        const IssueReceiveDropdown = ({ value, onChange, isActive, onToggle }) => {
            const ref = useRef(null);
            useEffect(() => {
                const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) onToggle(null); };
                if (isActive) document.addEventListener('mousedown', handler);
                return () => document.removeEventListener('mousedown', handler);
            }, [isActive]);
            const OPTIONS = [
                { id: '',  name: 'Tất cả', color: 'slate',   short: 'TC' },
                { id: 'N', name: 'Nhập',   color: 'emerald', short: 'N' },
                { id: 'X', name: 'Xuất',   color: 'red',     short: 'X' },
            ];
            const current = OPTIONS.find(o => o.id === value) || OPTIONS[0];
            const colorMap = {
                slate:   { dot: 'bg-slate-400',   ring: 'border-slate-200',   text: 'text-slate-600',   selBg: 'bg-slate-600',   selText: 'text-white' },
                emerald: { dot: 'bg-emerald-500', ring: 'border-emerald-200', text: 'text-emerald-700', selBg: 'bg-emerald-600', selText: 'text-white' },
                red:     { dot: 'bg-red-500',     ring: 'border-red-200',     text: 'text-red-700',     selBg: 'bg-red-600',     selText: 'text-white' },
            };
            const c = colorMap[current.color];
            return (
                <div className="relative" ref={ref}>
                    <div className="label-text">Nhập / Xuất</div>
                    <button type="button" onClick={() => onToggle(isActive ? null : 'issueReceive')}
                            className={`filter-control justify-between ${isActive ? 'active ring-2 ring-indigo-100 border-indigo-400' : ''}`}>
                        <span className="flex items-center gap-2">
                            <span className={`w-2 h-2 rounded-full ${c.dot}`}></span>
                            <span className={`font-black ${c.text}`}>{current.name}</span>
                        </span>
                        <Icon name="chevron-down" size={10} className={`transition-transform ${isActive ? 'rotate-180 text-indigo-600' : 'opacity-40'}`} />
                    </button>
                    {isActive && (
                        <div className="absolute top-full left-0 mt-2 w-48 bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.25)] border border-slate-200 z-[600] overflow-hidden">
                            {OPTIONS.map(opt => {
                                const oc = colorMap[opt.color];
                                const sel = value === opt.id;
                                return (
                                    <div key={opt.id || 'all'} onClick={() => { onChange(opt.id); onToggle(null); }}
                                         className={`flex items-center gap-3 px-4 py-3 cursor-pointer transition-all border-b last:border-b-0 border-slate-100 ${sel ? oc.selBg + ' ' + oc.selText + ' font-black' : 'hover:bg-slate-50 text-slate-700 font-bold'}`}>
                                        <span className={`w-7 h-7 rounded-lg flex items-center justify-center font-black text-[11px] ${sel ? 'bg-white/20 text-white' : 'bg-' + opt.color + '-50 ' + oc.text + ' border ' + oc.ring}`}>
                                            {opt.short}
                                        </span>
                                        <span className="text-[12px] flex-1">{opt.name}</span>
                                        {sel && <Icon name="check" size={12}/>}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            );
        };

        const DOC_TABS = [
            { id: 'ledger',    name: 'Danh sách chứng từ tổng hợp' },
            { id: 'purchase',  name: 'Danh sách chứng từ nhập kho' },
            { id: 'warehouse', name: 'Danh sách chứng từ kho' },
        ];

        const DocumentTabDropdown = ({ activeTab, setActiveTab }) => {
            const [open, setOpen] = useState(false);
            const [pos, setPos] = useState({ top: 0, left: 0 });
            const btnRef = useRef(null);
            const panelRef = useRef(null);
            const isDocTab = DOC_TABS.some(t => t.id === activeTab);
            const current = DOC_TABS.find(t => t.id === activeTab);

            const updatePos = () => {
                if (btnRef.current) {
                    const r = btnRef.current.getBoundingClientRect();
                    setPos({ top: r.bottom + 4, left: r.left });
                }
            };
            useEffect(() => {
                if (!open) return;
                updatePos();
                const onDown = (e) => {
                    if (panelRef.current?.contains(e.target)) return;
                    if (btnRef.current?.contains(e.target)) return;
                    setOpen(false);
                };
                document.addEventListener('mousedown', onDown);
                window.addEventListener('scroll', updatePos, true);
                window.addEventListener('resize', updatePos);
                return () => {
                    document.removeEventListener('mousedown', onDown);
                    window.removeEventListener('scroll', updatePos, true);
                    window.removeEventListener('resize', updatePos);
                };
            }, [open]);

            return (
                <>
                    <button ref={btnRef} onClick={() => setOpen(!open)} className={`tab-btn flex items-center gap-2 ${isDocTab ? 'active bg-white/5' : 'hover:bg-white/5'}`}>
                        <Icon name="table" size={12}/>
                        <span className="truncate max-w-[260px]">{isDocTab ? current.name : 'Danh sách chứng từ'}</span>
                        <Icon name="chevron-down" size={10} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
                    </button>
                    {open && createPortal(
                        <div ref={panelRef} style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 99999, width: 320 }} className="bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.35)] border border-slate-200 overflow-hidden">
                            <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 text-[9px] font-black text-slate-400 uppercase tracking-widest">Chọn danh sách</div>
                            {DOC_TABS.map(t => (
                                <div key={t.id}
                                     onClick={() => { setActiveTab(t.id); setOpen(false); }}
                                     className={`px-4 py-3 cursor-pointer transition-all border-b last:border-b-0 border-slate-100 flex items-center gap-2 ${activeTab === t.id ? 'bg-indigo-600 text-white font-black' : 'hover:bg-indigo-50 text-slate-700 font-bold'}`}>
                                    <Icon name="table" size={12} className={activeTab === t.id ? 'text-white' : 'text-slate-400'}/>
                                    <span className="text-[12px] flex-1">{t.name}</span>
                                    {activeTab === t.id && <Icon name="check" size={12}/>}
                                </div>
                            ))}
                        </div>,
                        document.body
                    )}
                </>
            );
        };

        
        const PageSizeDropdown = ({ value, onChange }) => {
            const [open, setOpen] = useState(false);
            const ref = React.useRef(null);
            
            React.useEffect(() => {
                const handler = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
                if (open) document.addEventListener('mousedown', handler);
                return () => document.removeEventListener('mousedown', handler);
            }, [open]);

            const options = [
                { value: 1000, label: '1,000 dòng' },
                { value: 10000, label: '10,000 dòng' },
                { value: 50000, label: '50,000 dòng' },
                { value: 100000, label: '100,000 dòng' },
                { value: 200000, label: '200,000 dòng' },
                { value: 500000, label: '500,000 dòng' },
            ];

            return (
                <div className="relative" ref={ref}>
                    <div 
                        onClick={() => setOpen(!open)}
                        className="flex items-center gap-1 bg-transparent text-[11px] font-black text-slate-700 outline-none cursor-pointer pr-1 select-none"
                    >
                        <span>{value.toLocaleString()} dòng</span>
                        <Icon name="chevron-down" size={12} className={`text-slate-400 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
                    </div>
                    
                    {open && (
                        <div className="absolute top-full mt-2 left-0 bg-white/90 backdrop-blur-xl border border-white/50 shadow-[0_8px_30px_rgb(0,0,0,0.12)] rounded-2xl z-[6000] min-w-[130px] overflow-hidden origin-top animate-in fade-in zoom-in-95 duration-200">
                            <div className="p-1 flex flex-col gap-0.5">
                                {options.map(opt => (
                                    <div
                                        key={opt.value}
                                        onClick={() => { onChange(opt.value); setOpen(false); }}
                                        className={`px-3 py-2.5 rounded-xl text-[11px] font-bold cursor-pointer transition-all ${value === opt.value ? 'bg-indigo-50 text-indigo-700 shadow-sm' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`}
                                    >
                                        {opt.label}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            );
        };

        const App = () => {
            const [groupByPurchase, setGroupByPurchase] = useState([]);
            const [toggleGroupRenderPurchase, setToggleGroupRenderPurchase] = useState(0);
            const purchaseScrollRef = useRef();

            const [groupByWarehouse, setGroupByWarehouse] = useState([]);
            const [toggleGroupRenderWarehouse, setToggleGroupRenderWarehouse] = useState(0);
            const warehouseScrollRef = useRef();
            const [groupByLedger, setGroupByLedger] = useState([]);
            const [toggleGroupRender, setToggleGroupRender] = useState(0); // Để ép update khi toggle expand
            const ledgerScrollRef = useRef();
            const [isLoggedIn, setIsLoggedIn] = useState(false);
            const [activeTab, setActiveTab] = useState('ledger');
            const [data, setData] = useState([]);
            const [reportData, setReportData] = useState({});
            const [monthList, setMonthList] = useState([]);
            const [monthlyData, setMonthlyData] = useState({});
            const [jobList, setJobList] = useState([]);
            const [jobData, setJobData] = useState({});
            const [reportType, setReportType] = useState('BC001');
            const [trialBalanceData, setTrialBalanceData] = useState([]);
            const [trialBalanceTotal, setTrialBalanceTotal] = useState(null);
            const [pendingReportType, setPendingReportType] = useState(null);
            const [showClearModal, setShowClearModal] = useState(false);
            const [meta, setMeta] = useState({ accounts: [], orgs: [], pr_details: [], tran_ids: [], jobs: [], items: [], products: [], expenses: [], warehouses: [], db_info: {}, global_total: 0 });
            const [loading, setLoading] = useState(false);
            const [loginLoading, setLoginLoading] = useState(false);
            const [loginError, setLoginError] = useState("");
            const [activeDropdown, setActiveDropdown] = useState(null);
            const [period, setPeriod] = useState({ year: 2026, type: 'month', value: 1 });
            const [filters, setFilters] = useState({ from_date: '01/01/2026', to_date: '31/01/2026', tran_ids: [], org_ids: [], acc_ids: [], contra_acc_ids: [], job_ids: [], pr_detail_ids: [], item_ids: [], product_ids: [], expense_ids: [], tran_no: '', page: 1, page_size: 10000 });
            const [pagination, setPagination] = useState({ total_rows: 0, total_pages: 1, page: 1 });
            const [summary, setSummary] = useState({ total_debit: 0, total_credit: 0 });
            const [colSearch, setColSearch] = useState({});
            const [refreshing, setRefreshing] = useState(false);
            const [filtersExpanded, setFiltersExpanded] = useState(false);

            // Sort state cho 3 danh sách. field=null → dùng default backend.
            const [ledgerSort, setLedgerSort]       = useState({ field: null, dir: 'desc' });
            

            const [purchaseSort, setPurchaseSort]   = useState({ field: null, dir: 'desc' });
            const [warehouseSort, setWarehouseSort] = useState({ field: null, dir: 'desc' });

            const cycleSort = (cur, field) => {
                // null → desc → asc → null
                if (cur.field !== field) return { field, dir: 'desc' };
                if (cur.dir === 'desc')  return { field, dir: 'asc' };
                return { field: null, dir: 'desc' };
            };

            const [loginData, setLoginData] = useState({ driver: "SQL Server", server: localStorage.getItem("iacc_server") || "", database: localStorage.getItem("iacc_db") || "", user: "", password: "" });
            const [showDriverDialog, setShowDriverDialog] = useState(false);
            const [driverInstalling, setDriverInstalling] = useState(false);
            const [driverDropdownOpen, setDriverDropdownOpen] = useState(false);
            const driverOptions = [
                { value: "ODBC Driver 17 for SQL Server", label: "ODBC Driver 17 for SQL Server" },
                { value: "ODBC Driver 13 for SQL Server", label: "ODBC Driver 13 for SQL Server" },
                { value: "SQL Server", label: "SQL Server (mặc định)" }
            ];

            // AbortController để hủy request cũ khi có request mới
            const abortRef = useRef(null);

            // Debounce colSearch 400ms — chờ người dùng ngừng gõ mới bắn query
            const debouncedColSearch = useDebounce(colSearch, 400);

            useEffect(() => {
                // Check driver khi app load
                fetch('/api/check_driver').then(r => r.json()).then(res => {
                    if (!res.has_driver) {
                        setShowDriverDialog(true);
                    }
                });

                fetch('/api/metadata').then(r => {
                    if (r.status === 401) { setIsLoggedIn(false); }
                    else return r.json();
                }).then(res => { if(res) { setMeta(res); setIsLoggedIn(true); } });
            }, []);

            useEffect(() => {
                if (period.type === 'custom') return;
                const { year, type, value } = period;
                let s, e;
                if (type==='month') { s = new Date(year, value-1, 1); e = new Date(year, value, 0); }
                else if (type==='quarter') { s = new Date(year, (value-1)*3, 1); e = new Date(year, value*3, 0); }
                else { s = new Date(year, 0, 1); e = new Date(year, 11, 31); }
                const f = (d) => `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()}`;
                setFilters(p => ({ ...p, from_date: f(s), to_date: f(e) }));
            }, [period]);

            const handleLogin = async (e) => {
                e.preventDefault();
                setLoginLoading(true);
                setLoginError("");
                try {
                    const r = await fetch('/api/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(loginData)
                    });
                    const res = await r.json();
                    if (res.status === 'ok') {
                        localStorage.setItem("iacc_server", loginData.server);
                        localStorage.setItem("iacc_db", loginData.database);
                        setIsLoggedIn(true);
                        const metaRes = await fetch('/api/metadata').then(r => r.json());
                        setMeta(metaRes);
                    } else {
                        setLoginError(res.message);
                    }
                } catch (err) {
                    setLoginError("Không thể kết nối đến Server Python.");
                } finally {
                    setLoginLoading(false);
                }
            };

            const handleLogout = async () => {
                await fetch('/api/logout', { method: 'POST' });
                setIsLoggedIn(false);
                setMeta({ accounts: [], orgs: [], pr_details: [], tran_ids: [], jobs: [], items: [], products: [], expenses: [], warehouses: [], db_info: {}, global_total: 0 });
            };

            const refreshMeta = async () => {
                setRefreshing(true);
                try {
                    await fetch('/api/metadata/refresh', { method: 'POST' });
                    const res = await fetch('/api/metadata').then(r => r.json());
                    if (res.status === 'ok') {
                        setMeta(res);
                        // Hiệu ứng "Done" nhẹ
                        const btn = document.getElementById('btn-refresh-meta');
                        if(btn) {
                            btn.classList.add('bg-emerald-500/20', 'text-emerald-400');
                            setTimeout(() => btn.classList.remove('bg-emerald-500/20', 'text-emerald-400'), 2000);
                        }
                    }
                } finally {
                    setRefreshing(false);
                }
            };

            const loadData = async (targetPage = 1, targetPageSize = filters.page_size, searchOverride = null) => {
                // Hủy request đang chạy nếu có
                if (abortRef.current) abortRef.current.abort();
                abortRef.current = new AbortController();

                setLoading(true);
                const cs = searchOverride !== null ? searchOverride : colSearch;
                // Các field TEXT dài cần tối thiểu 2 ký tự để tránh scan toàn bảng
                // Các field ID ngắn cho phép 1 ký tự (ví dụ: gõ "5" tìm TK bắt đầu bằng 5)
                const LONG_FIELDS = new Set(['s_desc','s_pr_name','s_exp_name','s_org_name','s_item_name','s_prod_name','tran_no']);
                const take = (key, val) => {
                    const v = (val || '').trim();
                    if (!v) return null;
                    if (LONG_FIELDS.has(key) && v.length < 2) return null;
                    return v;
                };
                const searchParams = {
                    s_date:     take('s_date',     cs.TRAN_DATE),
                    tran_no:    take('tran_no',    cs.TRAN_NO),
                    s_tran_id:  take('s_tran_id',  cs.TRAN_ID),
                    s_acc_id:   take('s_acc_id',   cs.ACCOUNT_ID),
                    s_contra_id:take('s_contra_id',cs.ACCOUNT_ID_CONTRA),
                    s_desc:     take('s_desc',     cs.DESCRIPTION),
                    s_pr_name:  take('s_pr_name',  cs.PR_DETAIL_NAME),
                    s_exp_name: take('s_exp_name', cs.EXPENSE_NAME),
                    s_org_id:   take('s_org_id',   cs.ORGANIZATION_ID),
                    s_org_name: take('s_org_name', cs.ORGANIZATION_NAME),
                    s_item_name:take('s_item_name',cs.ITEM_NAME),
                    s_prod_name:take('s_prod_name',cs.PRODUCT_NAME)
                };
                const cleanSearch = {};
                Object.keys(searchParams).forEach(k => { if(searchParams[k]) cleanSearch[k] = searchParams[k]; });

                const isGrouped = groupByLedger.length > 0;
                const isSearched = Object.keys(cleanSearch).length > 0;
                // Skip COUNT: chỉ đổi trang (page>1) khi filter không đổi — frontend biết total
                const extras = {};
                if (targetPage > 1 && targetPageSize === filters.page_size && pagination.total_rows > 0) {
                    extras.known_total = pagination.total_rows;
                    extras.known_deb   = summary.total_debit;
                    extras.known_crd   = summary.total_credit;
                }

                // Construct query parameters conditionally
                const query = new URLSearchParams();
                Object.keys(filters).forEach(k => {
                    if (k === 'page_size') {
                        query.set(k, targetPageSize);
                    } else if (k === 'page') {
                        query.set(k, targetPage);
                    } else if (Array.isArray(filters[k])) {
                        query.set(k, filters[k].join(','));
                    } else {
                        query.set(k, filters[k]);
                    }
                });
                Object.keys(cleanSearch).forEach(k => { query.set(k, cleanSearch[k]); });
                Object.keys(extras).forEach(k => { query.set(k, extras[k]); });
                
                if (ledgerSort.field) { query.set('order_by', ledgerSort.field); query.set('order_dir', ledgerSort.dir); }

                try {
                    const r = await fetch(`/api/ledger?${query.toString()}`, { signal: abortRef.current.signal });
                    if (r.status === 401) { setIsLoggedIn(false); return; }
                    const res = await r.json();
                    if (res.status === 'ok') {
                        setData(res.data);
                        setPagination(res.pagination);
                        setSummary(res.summary);
                        setFilters(p => ({ ...p, page: targetPage, page_size: targetPageSize }));
                    } else {
                        alert('Lỗi truy vấn LEDGER:\n\n' + (res.message || JSON.stringify(res)));
                    }
                } catch (err) {
                    if (err.name === 'AbortError') return; // Request bị hủy — bình thường, bỏ qua
                    alert('Lỗi kết nối API LEDGER:\n\n' + err.message);
                } finally { setLoading(false); }
            };

            
            // Reload khi sort đổi
            useEffect(() => {
                if (isLoggedIn && activeTab === 'ledger') loadData(1, filters.page_size);
            }, [ledgerSort]);
            

            // ============ PURCHASE TAB STATE & LOADER ============
            const [purchaseData, setPurchaseData] = useState([]);
            const [purchasePagination, setPurchasePagination] = useState({ total_rows: 0, total_pages: 1, page: 1 });
            const [purchaseSummary, setPurchaseSummary] = useState({ quantity: 0, quantity_wh: 0, discount: 0, vat_tax: 0, total: 0 });
            const [purchaseColSearch, setPurchaseColSearch] = useState({});
            const [purchaseFilters, setPurchaseFilters] = useState({ wh_ids: [], tran_no_search: '' });
            
            // PURCHASE VIRTUAL SCROLL & GROUPING
            const purchaseFlatData = useMemo(() => {
                let filteredData = purchaseData;
                const searchKeys = Object.keys(purchaseColSearch).filter(k => (purchaseColSearch[k] || '').trim() !== '');
                if (searchKeys.length > 0) {
                    filteredData = filteredData.filter(row => {
                        return searchKeys.every(k => {
                            const val = String(row[k] || '').toLowerCase();
                            const query = purchaseColSearch[k].trim().toLowerCase();
                            return val.includes(query);
                        });
                    });
                }
                return buildGroupedData(filteredData, groupByPurchase, ['TOTAL_AMOUNT']);
                // eslint-disable-next-line react-hooks/exhaustive-deps
            }, [purchaseData, groupByPurchase, toggleGroupRenderPurchase, purchaseColSearch]);
            
            const purchaseRowHeight = 28;
            const purchaseVS = useVirtualScroll(purchaseFlatData.length, purchaseRowHeight, purchaseScrollRef);

            const handleTogglePurchaseGroup = (id) => {
                expandState.set(id, !(expandState.has(id) ? expandState.get(id) : true));
                setToggleGroupRenderPurchase(v => v + 1);
            };


            // ============ WAREHOUSE TAB STATE & LOADER ============
            const [warehouseData, setWarehouseData] = useState([]);
            const [warehousePagination, setWarehousePagination] = useState({ total_rows: 0, total_pages: 1, page: 1 });
            const [warehouseSummary, setWarehouseSummary] = useState({ quantity: 0, quantity_extra: 0, amount: 0 });
            const [warehouseColSearch, setWarehouseColSearch] = useState({});
            const debouncedWhColSearch = useDebounce(warehouseColSearch, 400);
            const [warehouseLoading, setWarehouseLoading] = useState(false);
            const [warehouseFilters, setWarehouseFilters] = useState({ wh_ids: [], tran_no_search: '', issue_receive: '' });

            // WAREHOUSE VIRTUAL SCROLL & GROUPING
            const warehouseFlatData = useMemo(() => {
                let filteredData = warehouseData;
                const searchKeys = Object.keys(warehouseColSearch).filter(k => (warehouseColSearch[k] || '').trim() !== '');
                if (searchKeys.length > 0) {
                    filteredData = filteredData.filter(row => {
                        return searchKeys.every(k => {
                            const val = String(row[k] || '').toLowerCase();
                            const query = warehouseColSearch[k].trim().toLowerCase();
                            return val.includes(query);
                        });
                    });
                }
                return buildGroupedData(filteredData, groupByWarehouse, ['AMOUNT']);
                // eslint-disable-next-line react-hooks/exhaustive-deps
            }, [warehouseData, groupByWarehouse, toggleGroupRenderWarehouse, warehouseColSearch]);
            
            const warehouseRowHeight = 28;
            const warehouseVS = useVirtualScroll(warehouseFlatData.length, warehouseRowHeight, warehouseScrollRef);

            const handleToggleWarehouseGroup = (id) => {
                expandState.set(id, !(expandState.has(id) ? expandState.get(id) : true));
                setToggleGroupRenderWarehouse(v => v + 1);
            };

            const togglePurchaseFilter = (key, id) => {
                setPurchaseFilters(p => {
                    if (Array.isArray(p[key])) return { ...p, [key]: p[key].includes(id) ? p[key].filter(x=>x!==id) : [...p[key], id] };
                    return { ...p, [key]: id };
                });
            };
            const debouncedPurchaseColSearch = useDebounce(purchaseColSearch, 400);
            const [purchaseLoading, setPurchaseLoading] = useState(false);
            const [exportOpen, setExportOpen] = useState(null); // 'ledger' | 'purchase' | null
            const [exporting, setExporting] = useState(false);
            const [exportProgress, setExportProgress] = useState(null); // {phase, current, total}
            // Modal xác nhận xuất CSV (stream): { kind, mode, total } | null
            const [exportConfirm, setExportConfirm] = useState(null);
            // Sau khi tải xong: { file_path, filename, total } | null — hiện modal "Mở file / Mở folder"
            const [exportDone, setExportDone] = useState(null);

            const buildPurchaseQuery = (targetPage = 1, targetPageSize = filters.page_size, searchOverride = null, extra = {}) => {
                const cs = searchOverride !== null ? searchOverride : purchaseColSearch;
                const LONG = new Set(['s_desc','s_org_name','s_wh_name','s_exp_name','s_job_name','s_pr_name','tran_no','s_inv_no','s_po_no']);
                const take = (k,v) => {
                    const x = (v||'').trim();
                    if (!x) return null;
                    if (LONG.has(k) && x.length < 2) return null;
                    return x;
                };
                const sp = {
                    s_date:        take('s_date',        cs.TRAN_DATE),
                    s_vat_date:    take('s_vat_date',    cs.VAT_TRAN_DATE),
                    tran_no:       take('tran_no',       cs.TRAN_NO),
                    s_tran_id:     take('s_tran_id',     cs.TRAN_ID),
                    s_org_id:      take('s_org_id',      cs.ORGANIZATION_ID),
                    s_org_name:    take('s_org_name',    cs.ORGANIZATION_NAME),
                    s_wh_id:       take('s_wh_id',       cs.WAREHOUSE_ID),
                    s_wh_name:     take('s_wh_name',     cs.WAREHOUSE_NAME),
                    s_item_id:     take('s_item_id',     cs.ITEM_ID),
                    s_desc:        take('s_desc',        cs.DESCRIPTION),
                    s_inv_no:      take('s_inv_no',      cs.VAT_TRAN_NO),
                    s_po_no:       take('s_po_no',       cs.PO_TRAN_NO),
                    s_exp_id:      take('s_exp_id',      cs.EXPENSE_ID),
                    s_exp_name:    take('s_exp_name',    cs.EXPENSE_NAME),
                    s_job_id:      take('s_job_id',      cs.JOB_ID),
                    s_job_name:    take('s_job_name',    cs.JOB_NAME),
                    s_pr_id:       take('s_pr_id',       cs.PR_DETAIL_ID),
                    s_pr_name:     take('s_pr_name',     cs.PR_DETAIL_NAME),
                    s_acc_cost:    take('s_acc_cost',    cs.ACCOUNT_ID_COST),
                    s_unit_id:     take('s_unit_id',     cs.UNIT_ID),
                    s_unit_id_wh:  take('s_unit_id_wh',  cs.UNIT_ID_WH),
                };
                // Filter bổ sung: số CT (text), kho nhập (multi)
                if (purchaseFilters.tran_no_search?.trim()) sp.tran_no = purchaseFilters.tran_no_search.trim();
                const clean = {};
                Object.keys(sp).forEach(k => { if(sp[k]) clean[k] = sp[k]; });
                const query = new URLSearchParams({ ...filters, ...clean, ...extra, page: targetPage, page_size: targetPageSize });
                Object.keys(filters).forEach(k => { if(Array.isArray(filters[k])) query.set(k, filters[k].join(',')); });
                query.set('wh_ids', (purchaseFilters.wh_ids || []).join(','));
                if (purchaseSort.field) { query.set('order_by', purchaseSort.field); query.set('order_dir', purchaseSort.dir); }
                return query;
            };

            const loadPurchaseData = async (targetPage = 1, targetPageSize = filters.page_size, searchOverride = null) => {
                if (abortRef.current) abortRef.current.abort();
                abortRef.current = new AbortController();
                setPurchaseLoading(true);

                const cs = searchOverride !== null ? searchOverride : purchaseColSearch;
                const isGrouped = groupByPurchase.length > 0;
                const isSearched = Object.values(cs).some(val => (val || '').trim() !== '');
                const extras = {};
                if (targetPage > 1 && targetPageSize === filters.page_size && purchasePagination.total_rows > 0) {
                    extras.known_total = purchasePagination.total_rows;
                    extras.known_sums  = JSON.stringify(purchaseSummary);
                }

                // Construct query parameters conditionally
                const query = new URLSearchParams();
                Object.keys(filters).forEach(k => {
                    if (k === 'page_size') {
                        query.set(k, targetPageSize);
                    } else if (k === 'page') {
                        query.set(k, targetPage);
                    } else if (Array.isArray(filters[k])) {
                        query.set(k, filters[k].join(','));
                    } else {
                        query.set(k, filters[k]);
                    }
                });

                // Add purchase specific query logic
                const LONG = new Set(['s_desc','s_org_name','s_wh_name','s_exp_name','s_job_name','s_pr_name','tran_no','s_inv_no','s_po_no']);
                const take = (k,v) => {
                    const x = (v||'').trim();
                    if (!x) return null;
                    if (LONG.has(k) && x.length < 2) return null;
                    return x;
                };
                const sp = {
                    s_date:        take('s_date',        cs.TRAN_DATE),
                    s_vat_date:    take('s_vat_date',    cs.VAT_TRAN_DATE),
                    tran_no:       take('tran_no',       cs.TRAN_NO),
                    s_tran_id:     take('s_tran_id',     cs.TRAN_ID),
                    s_org_id:      take('s_org_id',      cs.ORGANIZATION_ID),
                    s_org_name:    take('s_org_name',    cs.ORGANIZATION_NAME),
                    s_wh_id:       take('s_wh_id',       cs.WAREHOUSE_ID),
                    s_wh_name:     take('s_wh_name',     cs.WAREHOUSE_NAME),
                    s_item_id:     take('s_item_id',     cs.ITEM_ID),
                    s_desc:        take('s_desc',        cs.DESCRIPTION),
                    s_inv_no:      take('s_inv_no',      cs.VAT_TRAN_NO),
                    s_po_no:       take('s_po_no',       cs.PO_TRAN_NO),
                    s_exp_id:      take('s_exp_id',      cs.EXPENSE_ID),
                    s_exp_name:    take('s_exp_name',    cs.EXPENSE_NAME),
                    s_job_id:      take('s_job_id',      cs.JOB_ID),
                    s_job_name:    take('s_job_name',    cs.JOB_NAME),
                    s_pr_id:       take('s_pr_id',       cs.PR_DETAIL_ID),
                    s_pr_name:     take('s_pr_name',     cs.PR_DETAIL_NAME),
                    s_acc_cost:    take('s_acc_cost',    cs.ACCOUNT_ID_COST),
                    s_unit_id:     take('s_unit_id',     cs.UNIT_ID),
                    s_unit_id_wh:  take('s_unit_id_wh',  cs.UNIT_ID_WH),
                };
                if (purchaseFilters.tran_no_search?.trim()) sp.tran_no = purchaseFilters.tran_no_search.trim();
                Object.keys(sp).forEach(k => { if(sp[k]) query.set(k, sp[k]); });
                Object.keys(extras).forEach(k => { query.set(k, extras[k]); });
                
                query.set('wh_ids', (purchaseFilters.wh_ids || []).join(','));
                if (purchaseSort.field) { query.set('order_by', purchaseSort.field); query.set('order_dir', purchaseSort.dir); }
                

                try {
                    const r = await fetch(`/api/purchase?${query.toString()}`, { signal: abortRef.current.signal });
                    if (r.status === 401) { setIsLoggedIn(false); return; }
                    const res = await r.json();
                    if (res.status === 'ok') {
                        setPurchaseData(res.data);
                        setPurchasePagination(res.pagination);
                        if (res.summary) setPurchaseSummary(res.summary);
                        setFilters(p => ({ ...p, page: targetPage, page_size: targetPageSize }));
                    } else {
                        alert('Lỗi truy vấn PURCHASE_VIEW:\n\n' + (res.message || JSON.stringify(res)));
                    }
                } catch (err) {
                    if (err.name === 'AbortError') return;
                    alert('Lỗi mạng / parse: ' + err.message);
                } finally { setPurchaseLoading(false); }
            };

            
            useEffect(() => {
                if (isLoggedIn && activeTab === 'purchase') loadPurchaseData(1, filters.page_size);
            }, [purchaseSort]);


            const toggleWarehouseFilter = (key, id) => {
                setWarehouseFilters(p => {
                    if (Array.isArray(p[key])) return { ...p, [key]: p[key].includes(id) ? p[key].filter(x=>x!==id) : [...p[key], id] };
                    return { ...p, [key]: id };
                });
            };

            // Đếm số filter đang active ở hàng 2 — hiện badge trên nút "Bộ lọc"
            const ledgerRow2Count = useMemo(() => (
                ['acc_ids','contra_acc_ids','pr_detail_ids','job_ids','expense_ids','item_ids','product_ids']
                    .reduce((n,k) => n + (filters[k]?.length || 0), 0)
            ), [filters]);
            const purchaseRow2Count = useMemo(() => (
                ['item_ids','expense_ids','job_ids','pr_detail_ids'].reduce((n,k) => n + (filters[k]?.length || 0), 0)
                + (purchaseFilters.wh_ids?.length || 0)
                + (purchaseFilters.tran_no_search?.trim() ? 1 : 0)
            ), [filters, purchaseFilters]);
            const warehouseRow2Count = useMemo(() => (
                ['item_ids','product_ids','expense_ids','job_ids','pr_detail_ids'].reduce((n,k) => n + (filters[k]?.length || 0), 0)
                + (warehouseFilters.wh_ids?.length || 0)
                + (warehouseFilters.tran_no_search?.trim() ? 1 : 0)
                + (warehouseFilters.issue_receive ? 1 : 0)
            ), [filters, warehouseFilters]);

            const buildWarehouseQuery = (targetPage = 1, targetPageSize = filters.page_size, searchOverride = null, extra = {}) => {
                const cs = searchOverride !== null ? searchOverride : warehouseColSearch;
                const LONG = new Set(['s_desc','s_org_name','s_wh_name','s_wh_name_issue','s_item_name','s_exp_name','s_job_name','s_pr_name','tran_no']);
                const take = (k,v) => {
                    const x = (v||'').trim();
                    if (!x) return null;
                    if (LONG.has(k) && x.length < 2) return null;
                    return x;
                };
                const sp = {
                    s_date:           take('s_date',           cs.TRAN_DATE),
                    tran_no:          take('tran_no',          cs.TRAN_NO),
                    s_tran_id:        take('s_tran_id',        cs.TRAN_ID),
                    s_org_id:         take('s_org_id',         cs.ORGANIZATION_ID),
                    s_org_name:       take('s_org_name',       cs.ORGANIZATION_NAME),
                    s_wh_id:          take('s_wh_id',          cs.WAREHOUSE_ID),
                    s_wh_name:        take('s_wh_name',        cs.WAREHOUSE_NAME),
                    s_wh_id_issue:    take('s_wh_id_issue',    cs.WAREHOUSE_ID_ISSUE),
                    s_wh_name_issue:  take('s_wh_name_issue',  cs.WAREHOUSE_NAME_ISSUE),
                    s_item_id:        take('s_item_id',        cs.ITEM_ID),
                    s_item_name:      take('s_item_name',      cs.ITEM_NAME),
                    s_exp_id:         take('s_exp_id',         cs.EXPENSE_ID),
                    s_exp_name:       take('s_exp_name',       cs.EXPENSE_NAME),
                    s_job_id:         take('s_job_id',         cs.JOB_ID),
                    s_job_name:       take('s_job_name',       cs.JOB_NAME),
                    s_pr_id:          take('s_pr_id',          cs.PR_DETAIL_ID),
                    s_pr_name:        take('s_pr_name',        cs.PR_DETAIL_NAME),
                    s_acc_id:         take('s_acc_id',         cs.ACCOUNT_ID),
                    s_acc_contra:     take('s_acc_contra',     cs.ACCOUNT_ID_CONTRA),
                    s_unit_id_wh:     take('s_unit_id_wh',     cs.UNIT_ID_WH),
                    s_unit_id_extra:  take('s_unit_id_extra',  cs.UNIT_ID_EXTRA),
                };
                if (warehouseFilters.tran_no_search?.trim()) sp.tran_no = warehouseFilters.tran_no_search.trim();
                if (warehouseFilters.issue_receive)          sp.issue_receive = warehouseFilters.issue_receive;
                const clean = {};
                Object.keys(sp).forEach(k => { if(sp[k]) clean[k] = sp[k]; });
                const query = new URLSearchParams({ ...filters, ...clean, ...extra, page: targetPage, page_size: targetPageSize });
                Object.keys(filters).forEach(k => { if(Array.isArray(filters[k])) query.set(k, filters[k].join(',')); });
                query.set('wh_ids', (warehouseFilters.wh_ids || []).join(','));
                if (warehouseSort.field) { query.set('order_by', warehouseSort.field); query.set('order_dir', warehouseSort.dir); }
                return query;
            };

            const loadWarehouseData = async (targetPage = 1, targetPageSize = filters.page_size, searchOverride = null) => {
                if (abortRef.current) abortRef.current.abort();
                abortRef.current = new AbortController();
                setWarehouseLoading(true);

                const cs = searchOverride !== null ? searchOverride : warehouseColSearch;
                const isGrouped = groupByWarehouse.length > 0;
                const isSearched = Object.values(cs).some(val => (val || '').trim() !== '');
                const extras = {};
                if (targetPage > 1 && targetPageSize === filters.page_size && warehousePagination.total_rows > 0) {
                    extras.known_total = warehousePagination.total_rows;
                    extras.known_sums  = JSON.stringify(warehouseSummary);
                }

                // Construct query parameters conditionally
                const query = new URLSearchParams();
                Object.keys(filters).forEach(k => {
                    if (k === 'page_size') {
                        query.set(k, targetPageSize);
                    } else if (k === 'page') {
                        query.set(k, targetPage);
                    } else if (Array.isArray(filters[k])) {
                        query.set(k, filters[k].join(','));
                    } else {
                        query.set(k, filters[k]);
                    }
                });

                // Add warehouse specific query logic
                const LONG = new Set(['s_desc','s_org_name','s_wh_name','s_wh_name_issue','s_item_name','s_exp_name','s_job_name','s_pr_name','tran_no']);
                const take = (k,v) => {
                    const x = (v||'').trim();
                    if (!x) return null;
                    if (LONG.has(k) && x.length < 2) return null;
                    return x;
                };
                const sp = {
                    s_date:           take('s_date',           cs.TRAN_DATE),
                    tran_no:          take('tran_no',          cs.TRAN_NO),
                    s_tran_id:        take('s_tran_id',        cs.TRAN_ID),
                    s_org_id:         take('s_org_id',         cs.ORGANIZATION_ID),
                    s_org_name:       take('s_org_name',       cs.ORGANIZATION_NAME),
                    s_wh_id:          take('s_wh_id',          cs.WAREHOUSE_ID),
                    s_wh_name:        take('s_wh_name',        cs.WAREHOUSE_NAME),
                    s_wh_id_issue:    take('s_wh_id_issue',    cs.WAREHOUSE_ID_ISSUE),
                    s_wh_name_issue:  take('s_wh_name_issue',  cs.WAREHOUSE_NAME_ISSUE),
                    s_item_id:        take('s_item_id',        cs.ITEM_ID),
                    s_item_name:      take('s_item_name',      cs.ITEM_NAME),
                    s_exp_id:         take('s_exp_id',         cs.EXPENSE_ID),
                    s_exp_name:       take('s_exp_name',       cs.EXPENSE_NAME),
                    s_job_id:         take('s_job_id',         cs.JOB_ID),
                    s_job_name:       take('s_job_name',       cs.JOB_NAME),
                    s_pr_id:          take('s_pr_id',          cs.PR_DETAIL_ID),
                    s_pr_name:        take('s_pr_name',        cs.PR_DETAIL_NAME),
                    s_acc_id:         take('s_acc_id',         cs.ACCOUNT_ID),
                    s_acc_contra:     take('s_acc_contra',     cs.ACCOUNT_ID_CONTRA),
                    s_unit_id_wh:     take('s_unit_id_wh',     cs.UNIT_ID_WH),
                    s_unit_id_extra:  take('s_unit_id_extra',  cs.UNIT_ID_EXTRA),
                };
                if (warehouseFilters.tran_no_search?.trim()) sp.tran_no = warehouseFilters.tran_no_search.trim();
                if (warehouseFilters.issue_receive)          sp.issue_receive = warehouseFilters.issue_receive;
                Object.keys(sp).forEach(k => { if(sp[k]) query.set(k, sp[k]); });
                Object.keys(extras).forEach(k => { query.set(k, extras[k]); });

                query.set('wh_ids', (warehouseFilters.wh_ids || []).join(','));
                if (warehouseSort.field) { query.set('order_by', warehouseSort.field); query.set('order_dir', warehouseSort.dir); }
                

                try {
                    const r = await fetch(`/api/warehouse?${query.toString()}`, { signal: abortRef.current.signal });
                    if (r.status === 401) { setIsLoggedIn(false); return; }
                    const res = await r.json();
                    if (res.status === 'ok') {
                        setWarehouseData(res.data);
                        setWarehousePagination(res.pagination);
                        if (res.summary) setWarehouseSummary(res.summary);
                        setFilters(p => ({ ...p, page: targetPage, page_size: targetPageSize }));
                    } else {
                        alert('Lỗi truy vấn WAREHOUSE_VIEW:\n\n' + (res.message || JSON.stringify(res)));
                    }
                } catch (err) {
                    if (err.name === 'AbortError') return;
                    alert('Lỗi mạng / parse: ' + err.message);
                } finally { setWarehouseLoading(false); }
            };

            
            useEffect(() => {
                if (isLoggedIn && activeTab === 'warehouse') loadWarehouseData(1, filters.page_size);
            }, [warehouseSort]);

            // ============ EXCEL EXPORT ============
            const LEDGER_EXPORT_COLS = [
                ['TRAN_DATE','Ngày CT'],['TRAN_NO','Số chứng từ'],['TRAN_ID','Mã CT'],['TRAN_NAME','Tên chứng từ'],
                ['ACCOUNT_ID','Tài khoản'],['ACCOUNT_ID_CONTRA','Đối ứng'],
                ['DESCRIPTION','Diễn giải'],
                ['DEBIT','Nợ'],['CREDIT','Có'],
                ['PR_DETAIL_ID','Mã ĐT'],['PR_DETAIL_NAME','Đối tượng'],
                ['PR_DETAIL_ID_CONTRA','Mã ĐT ĐƯ'],['PR_DETAIL_NAME_CONTRA','Đối tượng ĐƯ'],
                ['EXPENSE_ID','Mã MCP'],['EXPENSE_NAME','Mục chi phí'],
                ['EXPENSE_ID_CONTRA','Mã MCP ĐƯ'],['EXPENSE_NAME_CONTRA','Mục chi phí ĐƯ'],
                ['ORGANIZATION_ID','Mã ĐV'],['ORGANIZATION_NAME','Tên đơn vị'],
                ['ITEM_ID','Mã HH'],['ITEM_NAME','Hàng hóa'],
                ['ITEM_ID_CONTRA','Mã HH ĐƯ'],['ITEM_NAME_CONTRA','Hàng hóa ĐƯ'],
                ['JOB_ID','Mã CV'],['JOB_NAME','Công việc'],
                ['JOB_ID_CONTRA','Mã CV ĐƯ'],['JOB_NAME_CONTRA','Công việc ĐƯ'],
                ['PRODUCT_ID','Mã SP'],['PRODUCT_NAME','Sản phẩm'],
                ['BANK_ID','Mã NH'],['BANK_NAME','Ngân hàng'],
                ['BANK_ID_CONTRA','Mã NH ĐƯ'],['BANK_NAME_CONTRA','NH đối ứng']
            ];
            const WAREHOUSE_EXPORT_COLS = [
                ['ISSUE_RECEIVE','N/X'],
                ['ORGANIZATION_ID','Mã đơn vị'],['ORGANIZATION_NAME','Tên đơn vị'],
                ['TRAN_ID','Mã chứng từ'],['TRAN_NAME','Tên chứng từ'],['TRAN_NO','Số chứng từ'],['TRAN_DATE','Ngày chứng từ'],
                ['WAREHOUSE_ID','Mã kho'],['WAREHOUSE_NAME','Tên kho'],
                ['WAREHOUSE_ID_ISSUE','Mã kho xuất'],['WAREHOUSE_NAME_ISSUE','Tên kho xuất'],
                ['ITEM_ID','Mã hàng hóa'],['ITEM_NAME','Tên hàng hóa'],
                ['UNIT_ID_WH','ĐVT'],['QUANTITY','Số lượng'],
                ['UNIT_ID_EXTRA','ĐVT quy đổi'],['QUANTITY_EXTRA','SL quy đổi'],
                ['UNIT_PRICE','Đơn giá'],['AMOUNT','Thành tiền'],
                ['ACCOUNT_ID','Tài khoản'],['ACCOUNT_ID_CONTRA','TK đối ứng'],
                ['PR_DETAIL_ID','Mã đối tượng'],['PR_DETAIL_NAME','Tên đối tượng'],
                ['EXPENSE_ID','Mã MCP'],['EXPENSE_NAME','Tên MCP'],
                ['JOB_ID','Mã công việc'],['JOB_NAME','Tên công việc'],
            ];

            const PURCHASE_EXPORT_COLS = [
                ['ORGANIZATION_ID','Mã đơn vị'],['ORGANIZATION_NAME','Tên đơn vị'],
                ['TRAN_ID','Mã chứng từ'],['TRAN_NAME','Tên chứng từ'],['TRAN_NO','Số chứng từ'],['TRAN_DATE','Ngày chứng từ'],
                ['VAT_TRAN_NO','Số hóa đơn'],['VAT_TRAN_DATE','Ngày hóa đơn'],['PO_TRAN_NO','Số PO'],
                ['WAREHOUSE_ID','Mã kho'],['WAREHOUSE_NAME','Tên kho'],
                ['ITEM_ID','Mã hàng hóa'],['ITEM_NAME','Tên hàng hóa'],['DESCRIPTION','Diễn giải'],
                ['UNIT_ID','Đơn vị tính'],['QUANTITY','Số lượng'],
                ['UNIT_ID_WH','ĐVT kho'],['QUANTITY_WH','SL kho'],
                ['UNIT_PRICE','Đơn giá'],['DISCOUNT_AMOUNT','Giảm giá'],['PURCHASE_COST','Chi phí'],
                ['VAT_TAX_RATE','Thuế suất'],['VAT_TAX_AMOUNT','Tiền thuế VAT'],['TOTAL_AMOUNT','Tổng tiền'],
                ['ACCOUNT_ID_COST','TK kho'],
                ['PR_DETAIL_ID','Mã đối tượng'],['PR_DETAIL_NAME','Tên đối tượng'],
                ['EXPENSE_ID','Mã MCP'],['EXPENSE_NAME','Tên MCP'],
                ['JOB_ID','Mã công việc'],['JOB_NAME','Tên công việc']
            ];

            const orgNameMap = () => {
                const m = {};
                (meta.orgs || []).forEach(o => { m[(o.id||'').trim()] = o.name || ''; });
                return m;
            };

            // Extractors trả về MẢNG giá trị theo thứ tự cột (nhanh hơn build object ~3-5x cho data lớn)
            const extractLedgerRow = (r) => LEDGER_EXPORT_COLS.map(([key]) => {
                if (key === 'DEBIT')  return r.DEBIT_CREDIT === 'DEB' ? Number(r.AMOUNT || 0) : '';
                if (key === 'CREDIT') return r.DEBIT_CREDIT === 'CRD' ? Number(r.AMOUNT || 0) : '';
                const v = r[key];
                return v == null ? '' : v;
            });
            const extractRowGeneric = (cols, r) => cols.map(([key]) => {
                const v = r[key];
                return v == null ? '' : v;
            });

            const sanitizeSheetName = (s) => {
                const cleaned = String(s || 'Sheet').replace(/[\\/?*[\]:]/g, '_').substring(0, 31);
                return cleaned || 'Sheet';
            };

            // Excel hard limit: 1.048.576 dòng/sheet (kể cả header)
            const EXCEL_MAX_ROWS = 1048575;
            // Ngưỡng: trên ngưỡng này → server-side stream CSV (an toàn cho RAM browser)
            const SERVER_STREAM_THRESHOLD = 500000;
            // Ngưỡng cảnh báo per-sheet trong mode by_org
            const PER_SHEET_WARN = 200000;
            const yieldToUI = () => new Promise(r => setTimeout(r, 0));

            // Convert column index (0-based) → Excel column letter (A, B, ..., Z, AA, AB, ...)
            const colLetter = (idx) => {
                let s = '';
                idx = idx + 1;
                while (idx > 0) {
                    const m = (idx - 1) % 26;
                    s = String.fromCharCode(65 + m) + s;
                    idx = Math.floor((idx - 1) / 26);
                }
                return s;
            };

            // Tự build worksheet object — không gọi XLSX.utils.aoa_to_sheet (vốn enumerate properties).
            // Trả về ws object dạng {!ref, A1:{v,t}, ...} compatible XLSX writer.
            const buildSheetManual = async (cols, rows, extractor, onProgress) => {
                const headers = cols.map(([_, label]) => label);
                const truncate = rows.length > EXCEL_MAX_ROWS;
                const useRows = truncate ? rows.slice(0, EXCEL_MAX_ROWS) : rows;
                const ws = {};
                const nCols = headers.length;
                const nRows = useRows.length + 1; // +header

                // Header row
                for (let c = 0; c < nCols; c++) {
                    ws[colLetter(c) + '1'] = { v: headers[c], t: 's' };
                }

                const CHUNK = 10000;
                for (let i = 0; i < useRows.length; i++) {
                    const arr = extractor(useRows[i]);
                    const rowExcel = i + 2; // 1-based, +header
                    for (let c = 0; c < nCols; c++) {
                        const v = arr[c];
                        if (v === '' || v == null) continue; // skip empty cell
                        const ref = colLetter(c) + rowExcel;
                        if (typeof v === 'number') ws[ref] = { v, t: 'n' };
                        else                       ws[ref] = { v: String(v), t: 's' };
                    }
                    if (i > 0 && i % CHUNK === 0) {
                        if (onProgress) onProgress(i, useRows.length);
                        await yieldToUI();
                    }
                }
                if (onProgress) onProgress(useRows.length, useRows.length);

                ws['!ref'] = `A1:${colLetter(nCols - 1)}${nRows}`;
                return { ws, truncated: truncate ? rows.length - EXCEL_MAX_ROWS : 0 };
            };

            // Build query URLSearchParams cho count/stream — y hệt logic export-all của từng tab
            const buildExportQuery = (kind) => {
                if (kind === 'ledger') {
                    const query = new URLSearchParams({ ...filters });
                    Object.keys(filters).forEach(k => { if(Array.isArray(filters[k])) query.set(k, filters[k].join(',')); });
                    const cs = colSearch;
                    const map = {
                        s_date:cs.TRAN_DATE, tran_no:cs.TRAN_NO, s_tran_id:cs.TRAN_ID,
                        s_acc_id:cs.ACCOUNT_ID, s_contra_id:cs.ACCOUNT_ID_CONTRA,
                        s_desc:cs.DESCRIPTION, s_pr_name:cs.PR_DETAIL_NAME,
                        s_exp_name:cs.EXPENSE_NAME, s_org_id:cs.ORGANIZATION_ID,
                        s_org_name:cs.ORGANIZATION_NAME, s_item_name:cs.ITEM_NAME,
                        s_prod_name:cs.PRODUCT_NAME
                    };
                    Object.keys(map).forEach(k => { if((map[k]||'').trim()) query.set(k, map[k].trim()); });
                    if (ledgerSort.field) { query.set('order_by', ledgerSort.field); query.set('order_dir', ledgerSort.dir); }
                    return query;
                }
                if (kind === 'purchase') return buildPurchaseQuery(1, 1, null, {});
                return buildWarehouseQuery(1, 1, null, {});
            };

            // Trigger browser tải file qua URL (server-side stream). Không nạp vào RAM JS.
            const triggerDownload = (url, fname) => {
                const a = document.createElement('a');
                a.href = url;
                a.download = fname || '';
                document.body.appendChild(a);
                a.click();
                setTimeout(() => document.body.removeChild(a), 200);
            };

            // Kick off server-side export job → poll status → khi done set exportDone modal
            const startServerExport = async (kind, total) => {
                setExportConfirm(null);
                setExporting(true);
                setExportProgress({ phase: 'stream', current: 0, total });
                try {
                    const q = buildExportQuery(kind);
                    q.set('total', String(total));
                    const r = await fetch(`/api/${kind}/stream_csv?${q.toString()}`, { method: 'POST' });
                    const res = await r.json();
                    if (res.status !== 'ok' || !res.job_id) {
                        alert('Lỗi khởi tạo job xuất: ' + (res.message || 'unknown'));
                        return;
                    }
                    const jobId = res.job_id;
                    // Poll status mỗi 500ms cho đến khi done/error
                    while (true) {
                        await new Promise(r => setTimeout(r, 500));
                        const sr = await fetch(`/api/export/status?job_id=${jobId}`);
                        if (sr.status === 404) { alert('Job đã bị xóa.'); break; }
                        const sj = await sr.json();
                        setExportProgress({ phase: 'stream', current: sj.current || 0, total: sj.total || total });
                        if (sj.status === 'done') {
                            setExporting(false);
                            setExportProgress(null);
                            setExportDone({ file_path: sj.file_path, filename: sj.filename, total: sj.current });
                            break;
                        }
                        if (sj.status === 'error') {
                            alert('Lỗi xuất CSV: ' + (sj.error || ''));
                            break;
                        }
                    }
                } catch (err) {
                    alert('Lỗi: ' + err.message);
                } finally {
                    setExporting(false);
                    setExportProgress(null);
                }
            };

            const openExportedFile = async (path) => {
                try {
                    const r = await fetch('/api/open_file', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path })
                    });
                    const j = await r.json();
                    if (j.status !== 'ok') alert('Không mở được file: ' + (j.message || ''));
                } catch (e) { alert('Lỗi: ' + e.message); }
            };
            const openExportedFolder = async (path) => {
                try {
                    const r = await fetch('/api/open_folder', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path })
                    });
                    const j = await r.json();
                    if (j.status !== 'ok') alert('Không mở được folder: ' + (j.message || ''));
                } catch (e) { alert('Lỗi: ' + e.message); }
            };

            const doExport = async (kind, mode) => {
                // kind: 'ledger' | 'purchase' | 'warehouse' ; mode: 'single' | 'by_org'
                if (typeof XLSX === 'undefined') { alert('Thư viện XLSX chưa tải được. Vui lòng kiểm tra kết nối.'); return; }
                setExporting(true);
                setExportOpen(null);
                setExportProgress({ phase: 'fetch', current: 0, total: 0 });
                try {
                    // ===== BƯỚC 1: Lấy số dòng trước để quyết định route =====
                    const countQuery = buildExportQuery(kind);
                    const countRes = await fetch(`/api/${kind}/count?${countQuery.toString()}`).then(r => r.json()).catch(() => null);
                    const totalRows = countRes && countRes.status === 'ok' ? countRes.total : 0;

                    if (!totalRows) {
                        alert('Không có dữ liệu để xuất.');
                        return;
                    }

                    // ===== BƯỚC 2: HYBRID DECISION =====
                    // Mode "single" + > 500k dòng → server-side write to disk + modal Mở file/folder
                    if (mode === 'single' && totalRows > SERVER_STREAM_THRESHOLD) {
                        // Tắt overlay tạm thời, mở modal xác nhận thay
                        setExporting(false);
                        setExportProgress(null);
                        setExportConfirm({ kind, mode, total: totalRows });
                        return;
                    }

                    // ===== BƯỚC 3: client-side xlsx (nhỏ-vừa) =====
                    let url;
                    if (kind === 'ledger') {
                        url = `/api/ledger/export?${countQuery.toString()}`;
                    } else if (kind === 'purchase') {
                        url = `/api/purchase?${buildPurchaseQuery(1, 1, null, { export_all: '1' }).toString()}`;
                    } else {
                        url = `/api/warehouse?${buildWarehouseQuery(1, 1, null, { export_all: '1' }).toString()}`;
                    }

                    setExportProgress({ phase: 'fetch', current: 0, total: totalRows });
                    const r = await fetch(url);
                    if (r.status === 401) { setIsLoggedIn(false); return; }
                    const res = await r.json();
                    if (res.status !== 'ok') { alert('Lỗi xuất Excel: ' + (res.message || '')); return; }
                    const rows = res.data || [];
                    if (!rows.length) { alert('Không có dữ liệu để xuất.'); return; }

                    const cols = kind === 'ledger' ? LEDGER_EXPORT_COLS
                               : kind === 'purchase' ? PURCHASE_EXPORT_COLS
                               : WAREHOUSE_EXPORT_COLS;
                    const extractor = kind === 'ledger' ? extractLedgerRow : (r) => extractRowGeneric(cols, r);

                    const prefix = kind === 'ledger' ? 'ChungTuTongHop_' : (kind === 'purchase' ? 'PhieuNhapKho_' : 'ChungTuKho_');
                    const fname = prefix + filters.from_date.replace(/\//g,'') + '-' + filters.to_date.replace(/\//g,'') + '.xlsx';

                    setExportProgress({ phase: 'build', current: 0, total: rows.length });
                    await yieldToUI();

                    const wb = XLSX.utils.book_new();

                    if (mode === 'by_org') {
                        // Group theo ORGANIZATION_ID
                        const groups = new Map();
                        for (let i = 0; i < rows.length; i++) {
                            const id = (rows[i].ORGANIZATION_ID || '').toString().trim() || '__NONE__';
                            let g = groups.get(id);
                            if (!g) { g = []; groups.set(id, g); }
                            g.push(rows[i]);
                        }
                        const onm = orgNameMap();
                        const ids = [...groups.keys()].sort();
                        if (!ids.length) { alert('Không có dữ liệu để xuất.'); return; }

                        // Cảnh báo nếu có sheet con vượt PER_SHEET_WARN
                        const oversize = ids.filter(id => groups.get(id).length > PER_SHEET_WARN);
                        if (oversize.length) {
                            alert(
                                `Cảnh báo: ${oversize.length} đơn vị có dữ liệu vượt ${PER_SHEET_WARN.toLocaleString()} dòng — có thể gây nặng khi mở.\n\n` +
                                `Tiếp tục xuất bình thường, nhưng nên thu hẹp khoảng ngày.`
                            );
                        }

                        let done = 0;
                        for (const id of ids) {
                            const grp = groups.get(id);
                            const { ws } = await buildSheetManual(cols, grp, extractor, (c) => {
                                setExportProgress({ phase: 'build', current: done + c, total: rows.length });
                            });
                            const orgName = id === '__NONE__' ? 'Khac' : (onm[id] || id);
                            XLSX.utils.book_append_sheet(wb, ws, sanitizeSheetName(`${id}-${orgName}`));
                            done += grp.length;
                            setExportProgress({ phase: 'build', current: done, total: rows.length });
                            await yieldToUI();
                        }
                    } else {
                        const { ws } = await buildSheetManual(cols, rows, extractor, (c, t) => {
                            setExportProgress({ phase: 'build', current: c, total: t });
                        });
                        XLSX.utils.book_append_sheet(wb, ws, sanitizeSheetName('Data'));
                    }

                    setExportProgress({ phase: 'write', current: rows.length, total: rows.length });
                    await yieldToUI();

                    // Dùng XLSX.write + Blob → tránh writeFile internal heavy enumeration
                    const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array', compression: true });
                    const blob = new Blob([wbout], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
                    const blobUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = blobUrl;
                    a.download = fname;
                    document.body.appendChild(a);
                    a.click();
                    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(blobUrl); }, 100);
                } catch (err) {
                    alert('Lỗi xuất Excel: ' + (err && err.message ? err.message : String(err)));
                } finally {
                    setExporting(false);
                    setExportProgress(null);
                }
            };

            const ExportButton = ({ kind }) => {
                const ref = useRef(null);
                useEffect(() => {
                    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setExportOpen(null); };
                    if (exportOpen === kind) document.addEventListener('mousedown', onDown);
                    return () => document.removeEventListener('mousedown', onDown);
                }, [exportOpen]);
                return (
                    <div className="relative shrink-0" ref={ref}>
                        <button
                            type="button"
                            disabled={exporting}
                            onClick={() => setExportOpen(exportOpen === kind ? null : kind)}
                            className="group relative overflow-hidden bg-emerald-600 text-white px-3 h-[40px] rounded-xl font-black text-[10px] uppercase tracking-wider transition-all hover:bg-emerald-700 active:scale-[0.98] shadow-lg shadow-emerald-500/20 flex items-center gap-1.5 shrink-0"
                        >
                            {exporting ? <Icon name="loader" className="animate-spin" size={12}/> : <Icon name="file-spreadsheet" size={12}/>}
                            <span>{exporting ? 'Đang xuất...' : 'Xuất Excel'}</span>
                            <Icon name="chevron-down" size={9} className={`transition-transform ${exportOpen === kind ? 'rotate-180' : ''}`} />
                        </button>
                        {exportOpen === kind && (
                            <div className="absolute top-full right-0 mt-2 w-72 bg-white rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.25)] border border-slate-200 z-[600] overflow-hidden">
                                <div className="px-4 py-3 bg-emerald-50/50 border-b border-emerald-100">
                                    <div className="text-[9px] font-black text-emerald-700 uppercase tracking-widest">Chọn kiểu xuất</div>
                                </div>
                                <button onClick={() => doExport(kind, 'single')} className="w-full text-left px-4 py-3 hover:bg-slate-50 transition-all border-b border-slate-100">
                                    <div className="text-[12px] font-black text-slate-800">Tất cả vào 1 sheet</div>
                                    <div className="text-[10px] font-bold text-slate-400 mt-0.5">{`< 500k dòng: xlsx · ≥ 500k: tự stream CSV`}</div>
                                </button>
                                <button onClick={() => doExport(kind, 'by_org')} className="w-full text-left px-4 py-3 hover:bg-slate-50 transition-all">
                                    <div className="text-[12px] font-black text-slate-800">Mỗi đơn vị 1 sheet</div>
                                    <div className="text-[10px] font-bold text-slate-400 mt-0.5">Tách theo đơn vị · luôn xlsx</div>
                                </button>
                            </div>
                        )}
                    </div>
                );
            };

            const loadReportData = async () => {
                if (abortRef.current) abortRef.current.abort();
                abortRef.current = new AbortController();
                setLoading(true);
                const query = new URLSearchParams({ from_date: filters.from_date, to_date: filters.to_date, org_ids: filters.org_ids.join(','), job_ids: filters.job_ids.join(',') });
                try {
                    if (reportType === 'BC006') {
                        const r = await fetch(`/api/trial_balance?${query.toString()}`, { signal: abortRef.current.signal });
                        if (r.status === 401) { setIsLoggedIn(false); return; }
                        const res = await r.json();
                        if (res.status === 'ok') {
                            setTrialBalanceData(res.data);
                            setTrialBalanceTotal(res.total);
                        }
                    } else if (reportType === 'BC005') {
                        const r = await fetch(`/api/balance_sheet?${query.toString()}`, { signal: abortRef.current.signal });
                        if (r.status === 401) { setIsLoggedIn(false); return; }
                        const res = await r.json();
                        if (res.status === 'ok') {
                            setReportData(res.data);
                            setMonthList([]);
                            setMonthlyData({});
                            setJobList([]);
                            setJobData({});
                        }
                    } else if (reportType === 'BC007') {
                        const r = await fetch(`/api/journal?${query.toString()}`, { signal: abortRef.current.signal });
                        if (r.status === 401) { setIsLoggedIn(false); return; }
                        const res = await r.json();
                        if (res.status === 'ok') {
                            setReportData(res);
                        }
                    } else if (reportType === 'BC008') {
                        const r = await fetch(`/api/account_details?${query.toString()}&acc_ids=${filters.acc_ids.join(',')}`, { signal: abortRef.current.signal });
                        if (r.status === 401) { setIsLoggedIn(false); return; }
                        const res = await r.json();
                        if (res.status === 'ok') {
                            setReportData(res);
                        }
                    }
                } catch (err) {
                    if (err.name === 'AbortError') return;
                } finally { setLoading(false); }
            };

            
            // LEDGER VIRTUAL SCROLL & GROUPING
            const ledgerFlatData = useMemo(() => {
                let filteredData = data;
                const searchKeys = Object.keys(colSearch).filter(k => (colSearch[k] || '').trim() !== '');
                if (searchKeys.length > 0) {
                    filteredData = filteredData.filter(row => {
                        return searchKeys.every(k => {
                            const val = String(row[k] || '').toLowerCase();
                            const query = colSearch[k].trim().toLowerCase();
                            return val.includes(query);
                        });
                    });
                }
                return buildGroupedData(filteredData, groupByLedger, ['DEBIT', 'CREDIT']);
                // eslint-disable-next-line react-hooks/exhaustive-deps
            }, [data, groupByLedger, toggleGroupRender, colSearch]);
            
            const ledgerRowHeight = 28; // Chiều cao thực tế của <tr> không đổi theo filtersExpanded
            const ledgerVS = useVirtualScroll(ledgerFlatData.length, ledgerRowHeight, ledgerScrollRef);

            const handleToggleLedgerGroup = (id) => {
                expandState.set(id, !(expandState.has(id) ? expandState.get(id) : true));
                setToggleGroupRender(v => v + 1);
            };

            const toggleFilter = (key, id) => {
                if (key === 'from_date' || key === 'to_date') {
                    setFilters(p => ({ ...p, [key]: id }));
                } else {
                    setFilters(p => ({ ...p, [key]: p[key].includes(id) ? p[key].filter(x => x!==id) : [...p[key], id] }));
                }
            };

            if (!isLoggedIn) {
                return (
                    <div className="h-screen bg-slate-900 flex items-center justify-center relative overflow-hidden p-6">
                        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/20 blur-[120px] rounded-full"></div>
                        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-emerald-600/20 blur-[120px] rounded-full"></div>

                        {showDriverDialog && (
                            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[9999]">
                                <div className="bg-white rounded-3xl p-8 max-w-md shadow-2xl">
                                    <div className="flex items-center gap-3 mb-4">
                                        <Icon name="alert-circle" size={24} className="text-orange-500"/>
                                        <h2 className="text-xl font-black text-slate-900">ODBC Driver không cài đặt</h2>
                                    </div>
                                    <p className="text-slate-600 mb-6 text-sm">Ứng dụng phát hiện máy của bạn chưa cài ODBC Driver 17 for SQL Server. Bạn cần cài driver này để kết nối SQL Server.</p>
                                    <div className="space-y-3">
                                        <button
                                            disabled={driverInstalling}
                                            onClick={async () => {
                                                setDriverInstalling(true);
                                                const res = await fetch('/api/install_driver', {method: 'POST'});
                                                const data = await res.json();
                                                if (data.success) {
                                                    alert('✓ Cài đặt driver thành công! Vui lòng nhấn F5 (Làm mới trang) hoặc khởi động lại ứng dụng để bắt đầu sử dụng.');
                                                    setShowDriverDialog(false);
                                                } else {
                                                    alert('✗ Cài đặt thất bại: ' + data.message);
                                                }
                                                setDriverInstalling(false);
                                            }}
                                            className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold hover:bg-indigo-700 disabled:opacity-50"
                                        >
                                            {driverInstalling ? 'Đang cài đặt...' : 'Cài đặt driver ngay'}
                                        </button>
                                        <button
                                            onClick={() => setShowDriverDialog(false)}
                                            className="w-full bg-slate-100 text-slate-900 py-3 rounded-xl font-bold hover:bg-slate-200"
                                        >
                                            Bỏ qua (thử driver khác)
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        <div className="glass-login w-full max-w-md rounded-[32px] p-10 shadow-2xl z-10 relative border border-white/20">
                            <div className="text-center mb-8">
                                <svg viewBox="0 0 200 200" className="h-16 w-16 mx-auto mb-4">
                                    <rect width="200" height="200" rx="45" fill="#FF9D3D"/>
                                    <rect x="40" y="40" width="120" height="120" rx="30" fill="none" stroke="white" strokeWidth="20"/>
                                </svg>
                                <h1 className="text-2xl font-black text-slate-900 tracking-tight">{APP_NAME}</h1>
                                <p className="text-slate-500 font-bold text-[10px] uppercase tracking-widest mt-1">{APP_VERSION}</p>
                            </div>

                            <form onSubmit={handleLogin} className="space-y-4">

                                <div><div className="label-text mb-1.5 ml-1">Server Address</div><input required className="login-input" value={loginData.server} onChange={e => setLoginData({...loginData, server: e.target.value})}/></div>
                                <div><div className="label-text mb-1.5 ml-1">Database Name</div><input required className="login-input" value={loginData.database} onChange={e => setLoginData({...loginData, database: e.target.value})}/></div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div><div className="label-text mb-1.5 ml-1">User ID</div><input required className="login-input" value={loginData.user} onChange={e => setLoginData({...loginData, user: e.target.value})} placeholder="sa"/></div>
                                    <div><div className="label-text mb-1.5 ml-1">Password</div><input required type="password" className="login-input" value={loginData.password} onChange={e => setLoginData({...loginData, password: e.target.value})} placeholder="••••••••"/></div>
                                </div>

                                {loginError && <div className="bg-red-50 border border-red-100 text-red-600 p-3 rounded-xl text-[10px] font-bold flex items-center gap-2 mt-2 leading-tight animate-shake"><Icon name="lock" size={12}/> {loginError}</div>}

                                <button disabled={loginLoading} type="submit" className="w-full bg-indigo-600 text-white py-4 rounded-2xl font-black text-[12px] uppercase tracking-widest shadow-xl shadow-indigo-500/30 hover:bg-indigo-700 active:scale-[0.98] transition-all flex items-center justify-center gap-3 mt-6">
                                    {loginLoading ? <Icon name="loader" className="animate-spin"/> : <><Icon name="database" size={14}/> KẾT NỐI NGAY</>}
                                </button>
                            </form>
                            
                            <div className="mt-8 pt-8 border-t border-slate-200 text-center">
                                <p className="text-slate-400 font-bold text-[9px] uppercase tracking-widest italic">Designed for iPOS/IACC Performance</p>
                            </div>
                        </div>
                    </div>
                );
            }

            const isLedgerGroupedOrSearched = groupByLedger.length > 0 || Object.values(colSearch).some(val => (val || '').trim() !== '');
            const isPurchaseGroupedOrSearched = groupByPurchase.length > 0 || Object.values(purchaseColSearch).some(val => (val || '').trim() !== '');
            const isWarehouseGroupedOrSearched = groupByWarehouse.length > 0 || Object.values(warehouseColSearch).some(val => (val || '').trim() !== '');
            return (
                <div className="h-screen flex flex-col">
                    <div className="bg-slate-900 text-[10px] text-slate-400 px-6 py-1.5 flex justify-between items-center shrink-0 z-[1000]">
                        <div className="flex items-center gap-6"><div className="flex items-center gap-2"><div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></div><span className="font-black text-slate-200 uppercase tracking-widest">Connected</span></div><div className="font-black text-indigo-400 uppercase tracking-widest">{meta.db_info?.database}</div><div className="text-slate-500 font-bold">{APP_VERSION}</div></div>
                        <div className="flex bg-white/5 rounded-lg border border-white/10">
                            <DocumentTabDropdown activeTab={activeTab} setActiveTab={setActiveTab} />
                            <button onClick={() => setActiveTab('report')} className={`tab-btn flex items-center gap-2 ${activeTab === 'report' ? 'active bg-white/5' : 'hover:bg-white/5'}`}><Icon name="file-text" size={12}/> Báo cáo</button>
                        </div>
                        <div className="flex items-center gap-4">
                            <div className="font-black uppercase tracking-widest">Records: <span className="text-white">{meta.global_total?.toLocaleString()}</span></div>
                            <button id="btn-refresh-meta" onClick={refreshMeta} disabled={refreshing} title="Tải lại danh mục (Tài khoản, Đơn vị...)" className="bg-white/10 hover:bg-indigo-500/20 hover:text-indigo-400 p-1.5 px-3 rounded-lg transition-all flex items-center gap-2 font-black uppercase text-[9px]">
                                <Icon name="loader" size={10} className={refreshing ? 'animate-spin' : ''}/> 
                                {refreshing ? 'Đang tải...' : 'Danh mục'}
                            </button>
                            <button onClick={handleLogout} className="bg-white/10 hover:bg-red-500/20 hover:text-red-400 p-1.5 px-3 rounded-lg transition-all flex items-center gap-2 font-black uppercase text-[9px]"><Icon name="log-out" size={10}/> Đăng xuất</button>
                        </div>
                    </div>

                    {activeTab === 'ledger' && (
                        <>
                            <div className="bg-white border-b border-slate-200 p-4 px-6 shrink-0 shadow-sm z-[900]">
                                <div className="space-y-4">
                                    <div className="flex items-end gap-4">
                                        <div className="w-64"><PeriodDropdown period={period} setPeriod={setPeriod} isActive={activeDropdown === 'period'} onToggle={setActiveDropdown} /></div>
                                        <div className="w-32">
                                            <IOSDatePicker label="Từ ngày" value={filters.from_date} onChange={val => toggleFilter('from_date', val)} disabled={period.type !== 'custom'} />
                                        </div>
                                        <div className="w-32">
                                            <IOSDatePicker label="Đến ngày" value={filters.to_date} onChange={val => toggleFilter('to_date', val)} disabled={period.type !== 'custom'} />
                                        </div>
                                        <div className="w-40"><PremiumDropdown label="Loại CT" items={meta.tran_ids} selectedItems={filters.tran_ids} onSelect={id => toggleFilter('tran_ids', id)} isActive={activeDropdown === 'Loại CT'} onToggle={setActiveDropdown} /></div>
                                        <div className="w-40"><PremiumDropdown label="Đơn vị" items={meta.orgs} selectedItems={filters.org_ids} onSelect={id => toggleFilter('org_ids', id)} isActive={activeDropdown === 'Đơn vị'} onToggle={setActiveDropdown} align="right" /></div>
                                        
                                        {/* Khối hành động ĐẨY SÁT PHẢI TUYỆT ĐỐI */}
                                        <div className="ml-auto flex items-center gap-2">
                                            <div className="flex items-center gap-3 bg-slate-50 border border-slate-200/60 rounded-xl px-3 py-1 shrink-0 h-[40px]">
                                                <div className="flex flex-col items-start shrink-0">
                                                    <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.1em] mb-0.5">Hiển thị</span>
                                                    <PageSizeDropdown 
                                                        value={filters.page_size} 
                                                        onChange={newSize => { setFilters(p => ({ ...p, page_size: newSize, page: 1 })); }} 
                                                    />
                                                </div>
                                                <div className="h-6 w-px bg-slate-200"></div>
                                                <div className="flex flex-col items-end shrink-0">
                                                    <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.15em] mb-0.5">Results</span>
                                                    <div className="text-[12px] font-black text-indigo-600 tabular-nums leading-none tracking-tighter">
                                                        {pagination.total_rows?.toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>
                                            <button 
                                                onClick={() => loadData()} 
                                                disabled={loading} 
                                                className="group relative overflow-hidden bg-slate-900 text-white px-4 h-[40px] rounded-xl font-black text-[10px] uppercase tracking-wider transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-indigo-500/30 shrink-0"
                                            >
                                                <div className="absolute inset-0 bg-gradient-to-r from-indigo-600 to-violet-600 opacity-90 group-hover:opacity-100 transition-opacity"></div>
                                                <div className="relative flex items-center gap-2">
                                                    {loading && activeTab === 'ledger' ? (
                                                        <Icon name="loader" className="animate-spin" />
                                                    ) : (
                                                        <Icon name="search" size={12} className="group-hover:rotate-12 transition-transform"/>
                                                    )}
                                                    <span>{loading && activeTab === 'ledger' ? 'ĐANG TẢI...' : 'TRUY VẤN'}</span>
                                                </div>
                                            </button>
                                            <FilterToggleButton expanded={filtersExpanded} onToggle={() => setFiltersExpanded(v => !v)} count={ledgerRow2Count} />
                                            <ExportButton kind="ledger" />
                                        </div>
                                    </div>
                                    {filtersExpanded && <div className="grid grid-cols-7 gap-1.5">
                                        <PremiumDropdown label="Tài khoản" items={meta.accounts} selectedItems={filters.acc_ids} onSelect={id => toggleFilter('acc_ids', id)} isActive={activeDropdown === 'Tài khoản'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Đối ứng" items={meta.accounts} selectedItems={filters.contra_acc_ids} onSelect={id => toggleFilter('contra_acc_ids', id)} isActive={activeDropdown === 'Đối ứng'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Đối tượng" items={meta.pr_details} selectedItems={filters.pr_detail_ids} onSelect={id => toggleFilter('pr_detail_ids', id)} isActive={activeDropdown === 'Đối tượng'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Công việc" items={meta.jobs} selectedItems={filters.job_ids} onSelect={id => toggleFilter('job_ids', id)} isActive={activeDropdown === 'Công việc'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Mục chi phí" items={meta.expenses} selectedItems={filters.expense_ids} onSelect={id => toggleFilter('expense_ids', id)} isActive={activeDropdown === 'Mục chi phí'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Hàng hóa" items={meta.items} selectedItems={filters.item_ids} onSelect={id => toggleFilter('item_ids', id)} isActive={activeDropdown === 'Hàng hóa'} onToggle={setActiveDropdown} align="right" />
                                        <PremiumDropdown label="Sản phẩm" items={meta.products} selectedItems={filters.product_ids} onSelect={id => toggleFilter('product_ids', id)} isActive={activeDropdown === 'Sản phẩm'} onToggle={setActiveDropdown} align="right" />
                                    </div>}
                                </div>
                            </div>
                            <div className="flex-1 min-h-0 p-3 overflow-hidden bg-slate-50 flex flex-col relative">
                                {loading && <div className="absolute inset-0 bg-white/40 z-50 flex flex-col items-center justify-center backdrop-blur-[2px] transition-all"><div className="bg-white p-6 rounded-3xl shadow-2xl flex flex-col items-center gap-4 border border-indigo-50"><Icon name="loader" size={48} className="animate-spin text-indigo-600"/><div className="text-[10px] font-black text-indigo-600 uppercase tracking-widest animate-pulse">Đang truy vấn dữ liệu...</div></div></div>}
                                

                                <div className="bg-slate-100/80 border border-slate-200 rounded-xl p-2 mb-3 mx-6 mt-1 flex items-center gap-3 min-h-[44px] shadow-inner"
                                    onDragOver={e => e.preventDefault()}
                                    onDrop={e => {
                                        e.preventDefault();
                                        let col = e.dataTransfer.getData('text/plain');
                                        if (!col) col = e.dataTransfer.getData('col');
                                        if (col && !groupByLedger.includes(col)) setGroupByLedger([...groupByLedger, col]);
                                        
                                        const fromIdx = e.dataTransfer.getData('reorder');
                                        if (fromIdx !== '') {
                                            const arr = [...groupByLedger];
                                            const item = arr.splice(parseInt(fromIdx), 1)[0];
                                            arr.push(item);
                                            setGroupByLedger(arr);
                                        }
                                    }}
                                >
                                    <div className="bg-indigo-100 text-indigo-700 w-6 h-6 flex items-center justify-center rounded-lg shadow-sm">
                                        <Icon name="sliders" size={12}/>
                                    </div>
                                    <span className="text-[10px] text-slate-500 font-black uppercase tracking-widest">Khu vực gom nhóm:</span>
                                    {groupByLedger.length === 0 ? <span className="text-[10px] text-slate-400 italic">Kéo tiêu đề cột thả vào đây</span> : null}
                                    {groupByLedger.map((g, i) => (
                                        <div key={g} 
                                            draggable
                                            onDragStart={e => { e.stopPropagation(); e.dataTransfer.setData('reorder', i.toString()); }}
                                            onDragOver={e => e.preventDefault()}
                                            onDrop={e => {
                                                e.stopPropagation();
                                                e.preventDefault();
                                                const fromIdx = e.dataTransfer.getData('reorder');
                                                if (fromIdx !== '') {
                                                    const arr = [...groupByLedger];
                                                    const item = arr.splice(parseInt(fromIdx), 1)[0];
                                                    arr.splice(i, 0, item);
                                                    setGroupByLedger(arr);
                                                } else {
                                                    let col = e.dataTransfer.getData('text/plain');
                                                    if (!col) col = e.dataTransfer.getData('col');
                                                    if (col && !groupByLedger.includes(col)) {
                                                        const arr = [...groupByLedger];
                                                        arr.splice(i, 0, col);
                                                        setGroupByLedger(arr);
                                                    }
                                                }
                                            }}
                                            className="bg-white border border-indigo-200 text-indigo-700 px-3 py-1.5 rounded-full text-[10px] font-black flex items-center gap-2 shadow-sm animate-fade-in cursor-move">
                                            {g}
                                            <button onClick={() => setGroupByLedger(groupByLedger.filter(x => x !== g))} className="text-slate-300 hover:text-red-500 transition-colors bg-slate-50 hover:bg-red-50 rounded-full w-4 h-4 flex items-center justify-center"><Icon name="lock" size={8}/></button>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col mx-0">
                                    <div className="flex-1 min-h-0 overflow-auto custom-scrollbar" ref={ledgerScrollRef}>
                                        {/* Wrapper relative — ép scrollHeight = totalHeight để user scroll qua hết phần data ảo.
                                            Table position absolute với top = topPadding → rows luôn ở đúng vị trí logic */}
                                        <table className="w-max border-collapse" style={{ width: 'max-content', minWidth: '100%' }}>
                                            <thead className="sticky top-0 bg-slate-50/95 backdrop-blur-md z-30 shadow-sm">
                                                <tr className="text-slate-400 uppercase text-[9px] font-black tracking-widest text-center">
                                                    <th className="border-r w-14">#</th>
                                                    <SortableHeader field="TRAN_DATE"         sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-28">Ngày CT</SortableHeader>
                                                    <SortableHeader field="TRAN_NO"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-36 px-3">Số Chứng Từ</SortableHeader>
                                                    <SortableHeader field="TRAN_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-16">Mã CT</SortableHeader>
                                                    <SortableHeader field="TRAN_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-3">Tên chứng từ</SortableHeader>
                                                    <SortableHeader field="ACCOUNT_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Tài khoản</SortableHeader>
                                                    <SortableHeader field="ACCOUNT_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Đối ứng</SortableHeader>
                                                    <SortableHeader field="DESCRIPTION"       sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-64 px-3" align="left">Diễn giải</SortableHeader>
                                                    <SortableHeader field="AMOUNT"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="right">Nợ</SortableHeader>
                                                    <SortableHeader field="AMOUNT"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="right">Có</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã ĐT</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-56 px-3" align="left">Đối tượng</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã ĐT ĐƯ</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-56 px-3" align="left">Đối tượng ĐƯ</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã MCP</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Mục chi phí</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã MCP ĐƯ</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Mục chi phí ĐƯ</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_ID"   sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã ĐV</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_ID"   sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Tên Đơn vị</SortableHeader>
                                                    <SortableHeader field="ITEM_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã HH</SortableHeader>
                                                    <SortableHeader field="ITEM_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Hàng hóa</SortableHeader>
                                                    <SortableHeader field="ITEM_ID_CONTRA"    sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã HH ĐƯ</SortableHeader>
                                                    <SortableHeader field="ITEM_ID_CONTRA"    sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Hàng hóa ĐƯ</SortableHeader>
                                                    <SortableHeader field="JOB_ID"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã CV</SortableHeader>
                                                    <SortableHeader field="JOB_ID"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Công việc</SortableHeader>
                                                    <SortableHeader field="JOB_ID_CONTRA"     sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã CV ĐƯ</SortableHeader>
                                                    <SortableHeader field="JOB_ID_CONTRA"     sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Công việc ĐƯ</SortableHeader>
                                                    <SortableHeader field="PRODUCT_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã SP</SortableHeader>
                                                    <SortableHeader field="PRODUCT_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Sản phẩm</SortableHeader>
                                                    <SortableHeader field="BANK_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã NH</SortableHeader>
                                                    <SortableHeader field="BANK_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Ngân hàng</SortableHeader>
                                                    <SortableHeader field="BANK_ID_CONTRA"    sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã NH ĐƯ</SortableHeader>
                                                    <SortableHeader field="BANK_ID_CONTRA"    sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="w-44 px-4" align="left">NH đối ứng</SortableHeader>
                                                </tr>
                                                <tr className="bg-indigo-50/60 border-b-2 border-indigo-200">
                                                    {['','TRAN_DATE','TRAN_NO','TRAN_ID','TRAN_NAME','ACCOUNT_ID','ACCOUNT_ID_CONTRA','DESCRIPTION','','','PR_DETAIL_ID','PR_DETAIL_NAME','PR_DETAIL_ID_CONTRA','PR_DETAIL_NAME_CONTRA','EXPENSE_ID','EXPENSE_NAME','EXPENSE_ID_CONTRA','EXPENSE_NAME_CONTRA','ORGANIZATION_ID','ORGANIZATION_NAME','ITEM_ID','ITEM_NAME','ITEM_ID_CONTRA','ITEM_NAME_CONTRA','JOB_ID','JOB_NAME','JOB_ID_CONTRA','JOB_NAME_CONTRA','PRODUCT_ID','PRODUCT_NAME','BANK_ID','BANK_NAME','BANK_ID_CONTRA','BANK_NAME_CONTRA'].map((key, idx) => (
                                                        <th key={idx} className="border-r px-1 py-1">
                                                            {key ? <input
                                                                type="text"
                                                                value={colSearch[key] || ''}
                                                                onChange={e => setColSearch(p => ({...p, [key]: e.target.value}))}
                                                                className="w-full bg-white border border-slate-200 rounded-md px-1.5 py-1 text-[10px] font-semibold text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-200 focus:bg-indigo-50/30 transition-all placeholder:text-slate-300 placeholder:text-center"
                                                            /> : null}
                                                        </th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody className="text-[11px] font-medium text-slate-700">
                                                {ledgerVS.topPadding > 0 && <tr><td colSpan={100} style={{ height: ledgerVS.topPadding, padding: 0, border: 0 }}></td></tr>}
                                                {ledgerFlatData.slice(ledgerVS.startIndex, ledgerVS.endIndex + 1).map((row, i) => (
                                                    row.isGroup ?
                                                    <LedgerGroupRow key={row.id} node={row} toggleExpand={handleToggleLedgerGroup} /> :
                                                    <LedgerRow key={ledgerVS.startIndex + i} r={row} idx={ledgerVS.startIndex + i + 1} />
                                                ))}
                                                {ledgerVS.bottomPadding > 0 && <tr><td colSpan={100} style={{ height: ledgerVS.bottomPadding, padding: 0, border: 0 }}></td></tr>}
                                            </tbody>
                                            <tfoot className="sticky-footer">
                                                <tr className="text-slate-800 font-black text-[13px] bg-slate-50/95">
                                                    <td colSpan="8" className="border-r text-right px-8 py-3.5 uppercase text-[10px] text-slate-400">
                                                        Tổng toàn bộ truy vấn ({Number(pagination.total_rows||0).toLocaleString()} dòng):
                                                    </td>
                                                    <td className="border-r text-right px-4 text-emerald-700 bg-emerald-100/40">{summary.total_debit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                                                    <td className="border-r text-right px-4 text-red-700 bg-red-100/40">{summary.total_credit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                                                    <td colSpan="24"></td>
                                                </tr>
                                            </tfoot>
                                        </table>
                                    </div>
                                    <div className="p-4 bg-white border-t flex justify-between items-center px-10 shrink-0 z-40 shadow-inner">
                                        <div className="flex items-center gap-8">
                                            <div className="text-[10px] font-black text-slate-300 uppercase tracking-widest italic underline">iPOS Accounting Report</div>
                                        </div>
                                        <div className="flex items-center gap-6">
                                                <div className="flex items-center gap-2">
                                                    <button disabled={pagination.page <= 1} onClick={() => loadData(pagination.page - 1)} className="page-btn w-10 h-10 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-left" size={18}/></button>
                                                    <div className="flex items-center gap-2 px-4 py-1 bg-slate-50 rounded-2xl border border-slate-100">
                                                        <span className="text-[10px] font-black text-slate-400">TRANG</span>
                                                        <input type="number" min="1" max={pagination.total_pages} value={pagination.page} onChange={e => { const val = parseInt(e.target.value); if (val >= 1 && val <= pagination.total_pages) loadData(val); }} className="w-12 bg-transparent text-center font-black text-indigo-600 outline-none" />
                                                        <span className="text-[10px] font-black text-slate-400">/ {pagination.total_pages}</span>
                                                    </div>
                                                    <button disabled={pagination.page >= pagination.total_pages} onClick={() => loadData(pagination.page + 1)} className="page-btn w-10 h-10 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-right" size={18}/></button>
                                                </div>
                                            </div>
                                        <div className="flex flex-col items-end">
                                            <span className="text-[9px] font-black text-slate-300 uppercase tracking-tighter">Report Detail View</span>
                                            <span className="text-[11px] font-black text-indigo-400 uppercase tracking-widest">
                                                {isLedgerGroupedOrSearched ? `${data.length.toLocaleString()} dòng | Gom nhóm & tìm kiếm` : `Trang ${pagination.page} / ${pagination.total_pages}`}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}

                    {activeTab === 'purchase' && (
                        <>
                            <div className="bg-white border-b border-slate-200 p-4 px-6 shrink-0 shadow-sm z-[900]">
                                <div className="space-y-4">
                                    <div className="flex items-end gap-4">
                                        <div className="w-64"><PeriodDropdown period={period} setPeriod={setPeriod} isActive={activeDropdown === 'period'} onToggle={setActiveDropdown} /></div>
                                        <div className="w-32"><IOSDatePicker label="Từ ngày" value={filters.from_date} onChange={val => toggleFilter('from_date', val)} disabled={period.type !== 'custom'} /></div>
                                        <div className="w-32"><IOSDatePicker label="Đến ngày" value={filters.to_date} onChange={val => toggleFilter('to_date', val)} disabled={period.type !== 'custom'} /></div>
                                        <div className="w-40"><PremiumDropdown label="Loại CT" items={meta.tran_ids} selectedItems={filters.tran_ids} onSelect={id => toggleFilter('tran_ids', id)} isActive={activeDropdown === 'Loại CT'} onToggle={setActiveDropdown} /></div>
                                        <div className="w-40"><PremiumDropdown label="Đơn vị" items={meta.orgs} selectedItems={filters.org_ids} onSelect={id => toggleFilter('org_ids', id)} isActive={activeDropdown === 'Đơn vị'} onToggle={setActiveDropdown} align="right" /></div>
                                        <div className="ml-auto flex items-center gap-2">
                                            <div className="flex items-center gap-3 bg-slate-50 border border-slate-200/60 rounded-xl px-3 py-1 shrink-0 h-[40px]">
                                                <div className="flex flex-col items-start shrink-0">
                                                    <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.1em] mb-0.5">Hiển thị</span>
                                                    <PageSizeDropdown 
                                                        value={filters.page_size} 
                                                        onChange={newSize => {
                                                            setFilters(p => ({ ...p, page_size: newSize, page: 1 }));
                                                        }} 
                                                    />
                                                </div>
                                                <div className="h-6 w-px bg-slate-200"></div>
                                                <div className="flex flex-col items-end shrink-0">
                                                    <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.15em] mb-0.5">Results</span>
                                                    <div className="text-[12px] font-black text-indigo-600 tabular-nums leading-none tracking-tighter">
                                                        {purchasePagination.total_rows?.toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>
                                            <button onClick={() => loadPurchaseData()} disabled={purchaseLoading} className="group relative overflow-hidden bg-slate-900 text-white px-4 h-[40px] rounded-xl font-black text-[10px] uppercase tracking-wider transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-indigo-500/30 shrink-0">
                                                <div className="absolute inset-0 bg-gradient-to-r from-indigo-600 to-violet-600 opacity-90 group-hover:opacity-100 transition-opacity"></div>
                                                <div className="relative flex items-center gap-2">
                                                    {purchaseLoading ? <Icon name="loader" className="animate-spin" /> : <Icon name="search" size={12} className="group-hover:rotate-12 transition-transform"/>}
                                                    <span>{purchaseLoading ? 'ĐANG TẢI...' : 'TRUY VẤN'}</span>
                                                </div>
                                            </button>
                                            <FilterToggleButton expanded={filtersExpanded} onToggle={() => setFiltersExpanded(v => !v)} count={purchaseRow2Count} />
                                            <ExportButton kind="purchase" />
                                        </div>
                                    </div>
                                    {filtersExpanded && <div className="grid grid-cols-6 gap-1.5">
                                        <PremiumDropdown label="Hàng hóa" items={meta.items} selectedItems={filters.item_ids} onSelect={id => toggleFilter('item_ids', id)} isActive={activeDropdown === 'Hàng hóa'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Mục chi phí" items={meta.expenses} selectedItems={filters.expense_ids} onSelect={id => toggleFilter('expense_ids', id)} isActive={activeDropdown === 'Mục chi phí'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Công việc" items={meta.jobs} selectedItems={filters.job_ids} onSelect={id => toggleFilter('job_ids', id)} isActive={activeDropdown === 'Công việc'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Đối tượng" items={meta.pr_details} selectedItems={filters.pr_detail_ids} onSelect={id => toggleFilter('pr_detail_ids', id)} isActive={activeDropdown === 'Đối tượng'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Kho nhập" items={meta.warehouses} selectedItems={purchaseFilters.wh_ids} onSelect={id => togglePurchaseFilter('wh_ids', id)} isActive={activeDropdown === 'Kho nhập'} onToggle={setActiveDropdown} />
                                        <div>
                                            <div className="label-text">Số chứng từ</div>
                                            <input type="text" value={purchaseFilters.tran_no_search} onChange={e => setPurchaseFilters(p => ({...p, tran_no_search: e.target.value}))} placeholder="Nhập số CT..." className="filter-control text-[11px] font-bold" />
                                        </div>
                                    </div>}
                                </div>
                            </div>
                            <div className="flex-1 min-h-0 p-3 overflow-hidden bg-slate-50 flex flex-col relative">
                                {purchaseLoading && <div className="absolute inset-0 bg-white/40 z-50 flex flex-col items-center justify-center backdrop-blur-[2px] transition-all"><div className="bg-white p-6 rounded-3xl shadow-2xl flex flex-col items-center gap-4 border border-indigo-50"><Icon name="loader" size={48} className="animate-spin text-indigo-600"/><div className="text-[10px] font-black text-indigo-600 uppercase tracking-widest animate-pulse">Đang truy vấn dữ liệu...</div></div></div>}
                                

                                <div className="bg-slate-100/80 border border-slate-200 rounded-xl p-2 mb-3 mx-6 mt-1 flex items-center gap-3 min-h-[44px] shadow-inner"
                                    onDragOver={e => e.preventDefault()}
                                    onDrop={e => {
                                        e.preventDefault();
                                        let col = e.dataTransfer.getData('text/plain');
                                        if (!col) col = e.dataTransfer.getData('col');
                                        if (col && !groupByPurchase.includes(col)) setGroupByPurchase([...groupByPurchase, col]);
                                        
                                        const fromIdx = e.dataTransfer.getData('reorder');
                                        if (fromIdx !== '') {
                                            const arr = [...groupByPurchase];
                                            const item = arr.splice(parseInt(fromIdx), 1)[0];
                                            arr.push(item);
                                            setGroupByPurchase(arr);
                                        }
                                    }}
                                >
                                    <div className="bg-indigo-100 text-indigo-700 w-6 h-6 flex items-center justify-center rounded-lg shadow-sm">
                                        <Icon name="sliders" size={12}/>
                                    </div>
                                    <span className="text-[10px] text-slate-500 font-black uppercase tracking-widest">Khu vực gom nhóm:</span>
                                    {groupByPurchase.length === 0 ? <span className="text-[10px] text-slate-400 italic">Kéo tiêu đề cột thả vào đây</span> : null}
                                    {groupByPurchase.map((g, i) => (
                                        <div key={g} 
                                            draggable
                                            onDragStart={e => { e.stopPropagation(); e.dataTransfer.setData('reorder', i.toString()); }}
                                            onDragOver={e => e.preventDefault()}
                                            onDrop={e => {
                                                e.stopPropagation();
                                                e.preventDefault();
                                                const fromIdx = e.dataTransfer.getData('reorder');
                                                if (fromIdx !== '') {
                                                    const arr = [...groupByPurchase];
                                                    const item = arr.splice(parseInt(fromIdx), 1)[0];
                                                    arr.splice(i, 0, item);
                                                    setGroupByPurchase(arr);
                                                } else {
                                                    let col = e.dataTransfer.getData('text/plain');
                                                    if (!col) col = e.dataTransfer.getData('col');
                                                    if (col && !groupByPurchase.includes(col)) {
                                                        const arr = [...groupByPurchase];
                                                        arr.splice(i, 0, col);
                                                        setGroupByPurchase(arr);
                                                    }
                                                }
                                            }}
                                            className="bg-white border border-indigo-200 text-indigo-700 px-3 py-1.5 rounded-full text-[10px] font-black flex items-center gap-2 shadow-sm animate-fade-in cursor-move">
                                            {g}
                                            <button onClick={() => setGroupByPurchase(groupByPurchase.filter(x => x !== g))} className="text-slate-300 hover:text-red-500 transition-colors bg-slate-50 hover:bg-red-50 rounded-full w-4 h-4 flex items-center justify-center"><Icon name="lock" size={8}/></button>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col mx-0">
                                    <div className="flex-1 min-h-0 overflow-auto custom-scrollbar" ref={purchaseScrollRef}>
                                        <table className="w-max border-collapse" style={{ width: 'max-content', minWidth: '100%' }}>
                                            <thead className="sticky top-0 bg-slate-50/95 backdrop-blur-md z-30 shadow-sm">
                                                <tr className="text-slate-400 uppercase text-[9px] font-black tracking-widest text-center">
                                                    <th className="border-r w-12">#</th>
                                                    <SortableHeader field="ORGANIZATION_ID"   sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-20">Mã ĐV</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_NAME" sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-40 px-3" align="left">Tên đơn vị</SortableHeader>
                                                    <SortableHeader field="TRAN_ID"           sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-16">Mã CT</SortableHeader>
                                                    <SortableHeader field="TRAN_ID"           sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-40 px-3">Tên chứng từ</SortableHeader>
                                                    <SortableHeader field="TRAN_NO"           sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-32 px-3">Số CT</SortableHeader>
                                                    <SortableHeader field="TRAN_DATE"         sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24">Ngày CT</SortableHeader>
                                                    <SortableHeader field="VAT_TRAN_NO"       sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-28 px-2">Số HĐ</SortableHeader>
                                                    <SortableHeader field="VAT_TRAN_DATE"     sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24">Ngày HĐ</SortableHeader>
                                                    <SortableHeader field="PO_TRAN_NO"        sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24">Số PO</SortableHeader>
                                                    <SortableHeader field="WAREHOUSE_ID"      sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-20">Mã kho</SortableHeader>
                                                    <SortableHeader field="WAREHOUSE_NAME"    sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-36 px-3" align="left">Tên kho</SortableHeader>
                                                    <SortableHeader field="ITEM_ID"           sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24">Mã hàng</SortableHeader>
                                                    <SortableHeader field="DESCRIPTION"       sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-56 px-3" align="left">Diễn giải</SortableHeader>
                                                    <SortableHeader field="UNIT_ID"           sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-16">ĐVT</SortableHeader>
                                                    <SortableHeader field="QUANTITY"          sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24 px-2" align="right">Số lượng</SortableHeader>
                                                    <SortableHeader field="UNIT_ID_WH"        sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-16">ĐVT kho</SortableHeader>
                                                    <SortableHeader field="QUANTITY_WH"       sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24 px-2" align="right">SL kho</SortableHeader>
                                                    <SortableHeader field="UNIT_PRICE"        sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-28 px-2" align="right">Đơn giá</SortableHeader>
                                                    <SortableHeader field="DISCOUNT_AMOUNT"   sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24 px-2" align="right">Giảm giá</SortableHeader>
                                                    <SortableHeader field="PURCHASE_COST"     sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-28 px-2" align="right">Chi phí</SortableHeader>
                                                    <SortableHeader field="VAT_TAX_RATE"      sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-16">Thuế %</SortableHeader>
                                                    <SortableHeader field="VAT_TAX_AMOUNT"    sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-28 px-2" align="right">Tiền thuế</SortableHeader>
                                                    <SortableHeader field="TOTAL_AMOUNT"      sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-32 px-2" align="right">Tổng tiền</SortableHeader>
                                                    <SortableHeader field="ACCOUNT_ID_COST"   sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-20">TK kho</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID"      sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24">Mã ĐT</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_NAME"    sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-40 px-3" align="left">Tên đối tượng</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID"        sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24">Mã MCP</SortableHeader>
                                                    <SortableHeader field="EXPENSE_NAME"      sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-36 px-3" align="left">Tên MCP</SortableHeader>
                                                    <SortableHeader field="JOB_ID"            sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="border-r w-24">Mã CV</SortableHeader>
                                                    <SortableHeader field="JOB_NAME"          sort={purchaseSort} onSort={f => setPurchaseSort(s => cycleSort(s, f))} className="w-36 px-3" align="left">Tên công việc</SortableHeader>
                                                </tr>
                                                <tr className="bg-indigo-50/60 border-b-2 border-indigo-200">
                                                    {['','ORGANIZATION_ID','ORGANIZATION_NAME','TRAN_ID','TRAN_NAME','TRAN_NO','TRAN_DATE','VAT_TRAN_NO','VAT_TRAN_DATE','PO_TRAN_NO','WAREHOUSE_ID','WAREHOUSE_NAME','ITEM_ID','DESCRIPTION','UNIT_ID','','UNIT_ID_WH','','','','','','','','ACCOUNT_ID_COST','PR_DETAIL_ID','PR_DETAIL_NAME','EXPENSE_ID','EXPENSE_NAME','JOB_ID','JOB_NAME'].map((key, idx) => (
                                                        <th key={idx} className="border-r px-1 py-1">
                                                            {key ? <input
                                                                type="text"
                                                                value={purchaseColSearch[key] || ''}
                                                                onChange={e => setPurchaseColSearch(p => ({...p, [key]: e.target.value}))}
                                                                className="w-full bg-white border border-slate-200 rounded-md px-1.5 py-1 text-[10px] font-semibold text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-200 focus:bg-indigo-50/30 transition-all placeholder:text-slate-300 placeholder:text-center"
                                                            /> : null}
                                                        </th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody className="text-[11px] font-medium text-slate-700">
                                                {purchaseVS.topPadding > 0 && <tr><td colSpan={100} style={{ height: purchaseVS.topPadding, padding: 0, border: 0 }}></td></tr>}
                                                {purchaseFlatData.slice(purchaseVS.startIndex, purchaseVS.endIndex + 1).map((row, i) => (
                                                    row.isGroup ?
                                                    <PurchaseGroupRow key={row.id} node={row} toggleExpand={handleTogglePurchaseGroup} /> :
                                                    <PurchaseRow key={purchaseVS.startIndex + i} r={row} idx={purchaseVS.startIndex + i + 1} />
                                                ))}
                                                {purchaseVS.bottomPadding > 0 && <tr><td colSpan={100} style={{ height: purchaseVS.bottomPadding, padding: 0, border: 0 }}></td></tr>}
                                            </tbody>
                                            <tfoot className="sticky-footer">
                                                <tr className="text-slate-800 font-black text-[12px] bg-slate-50/95">
                                                    <td colSpan="15" className="border-r text-right px-4 py-3 uppercase text-[10px] text-slate-400">
                                                        Tổng toàn bộ truy vấn ({Number(purchasePagination.total_rows||0).toLocaleString()} dòng):
                                                    </td>
                                                    <td className="border-r text-right font-mono px-2 bg-slate-100/40">{Number(purchaseSummary.quantity||0).toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2})}</td>
                                                    <td className="border-r"></td>
                                                    <td className="border-r text-right font-mono px-2 bg-slate-100/40">{Number(purchaseSummary.quantity_wh||0).toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2})}</td>
                                                    <td className="border-r"></td>
                                                    <td className="border-r text-right font-mono px-2 text-orange-700 bg-orange-100/40">{Math.round(Number(purchaseSummary.discount||0)).toLocaleString('en-US')}</td>
                                                    <td colSpan="2" className="border-r"></td>
                                                    <td className="border-r text-right font-mono px-2 text-violet-700 bg-violet-100/40">{Math.round(Number(purchaseSummary.vat_tax||0)).toLocaleString('en-US')}</td>
                                                    <td className="border-r text-right font-mono px-2 text-emerald-700 bg-emerald-100/40">{Math.round(Number(purchaseSummary.total||0)).toLocaleString('en-US')}</td>
                                                    <td colSpan="7"></td>
                                                </tr>
                                            </tfoot>
                                        </table>
                                    </div>
                                    <div className="p-4 bg-white border-t flex justify-between items-center px-10 shrink-0 z-40 shadow-inner">
                                        <div className="flex items-center gap-8">
                                            <div className="text-[10px] font-black text-slate-300 uppercase tracking-widest italic underline">iPOS Accounting Report</div>
                                        </div>
                                        <div className="flex items-center gap-6">
                                                <div className="flex items-center gap-2">
                                                    <button disabled={purchasePagination.page <= 1} onClick={() => loadPurchaseData(purchasePagination.page - 1)} className="page-btn w-10 h-10 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-left" size={18}/></button>
                                                    <div className="flex items-center gap-2 px-4 py-1 bg-slate-50 rounded-2xl border border-slate-100">
                                                        <span className="text-[10px] font-black text-slate-400">TRANG</span>
                                                        <input type="number" min="1" max={purchasePagination.total_pages} value={purchasePagination.page} onChange={e => { const val = parseInt(e.target.value); if (val >= 1 && val <= purchasePagination.total_pages) loadPurchaseData(val); }} className="w-12 bg-transparent text-center font-black text-indigo-600 outline-none" />
                                                        <span className="text-[10px] font-black text-slate-400">/ {purchasePagination.total_pages}</span>
                                                    </div>
                                                    <button disabled={purchasePagination.page >= purchasePagination.total_pages} onClick={() => loadPurchaseData(purchasePagination.page + 1)} className="page-btn w-10 h-10 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-right" size={18}/></button>
                                                </div>
                                            </div>
                                        <div className="flex flex-col items-end">
                                            <span className="text-[9px] font-black text-slate-300 uppercase tracking-tighter">Purchase Detail View</span>
                                            <span className="text-[11px] font-black text-indigo-400 uppercase tracking-widest">
                                                {isPurchaseGroupedOrSearched ? `${purchaseData.length.toLocaleString()} dòng | Gom nhóm & tìm kiếm` : `Trang ${purchasePagination.page} / ${purchasePagination.total_pages}`}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}

                    {activeTab === 'warehouse' && (
                        <>
                            <div className="bg-white border-b border-slate-200 p-4 px-6 shrink-0 shadow-sm z-[900]">
                                <div className="space-y-4">
                                    <div className="flex items-end gap-4">
                                        <div className="w-64"><PeriodDropdown period={period} setPeriod={setPeriod} isActive={activeDropdown === 'period'} onToggle={setActiveDropdown} /></div>
                                        <div className="w-32"><IOSDatePicker label="Từ ngày" value={filters.from_date} onChange={val => toggleFilter('from_date', val)} disabled={period.type !== 'custom'} /></div>
                                        <div className="w-32"><IOSDatePicker label="Đến ngày" value={filters.to_date} onChange={val => toggleFilter('to_date', val)} disabled={period.type !== 'custom'} /></div>
                                        <div className="w-40"><PremiumDropdown label="Loại CT" items={meta.tran_ids} selectedItems={filters.tran_ids} onSelect={id => toggleFilter('tran_ids', id)} isActive={activeDropdown === 'Loại CT'} onToggle={setActiveDropdown} /></div>
                                        <div className="w-40"><PremiumDropdown label="Đơn vị" items={meta.orgs} selectedItems={filters.org_ids} onSelect={id => toggleFilter('org_ids', id)} isActive={activeDropdown === 'Đơn vị'} onToggle={setActiveDropdown} align="right" /></div>
                                        <div className="ml-auto flex items-center gap-2">
                                            <div className="flex items-center gap-3 bg-slate-50 border border-slate-200/60 rounded-xl px-3 py-1 shrink-0 h-[40px]">
                                                <div className="flex flex-col items-start shrink-0">
                                                    <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.1em] mb-0.5">Hiển thị</span>
                                                    <PageSizeDropdown 
                                                        value={filters.page_size} 
                                                        onChange={newSize => {
                                                            setFilters(p => ({ ...p, page_size: newSize, page: 1 }));
                                                        }} 
                                                    />
                                                </div>
                                                <div className="h-6 w-px bg-slate-200"></div>
                                                <div className="flex flex-col items-end shrink-0">
                                                    <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.15em] mb-0.5">Results</span>
                                                    <div className="text-[12px] font-black text-indigo-600 tabular-nums leading-none tracking-tighter">
                                                        {warehousePagination.total_rows?.toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>
                                            <button onClick={() => loadWarehouseData()} disabled={warehouseLoading} className="group relative overflow-hidden bg-slate-900 text-white px-4 h-[40px] rounded-xl font-black text-[10px] uppercase tracking-wider transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-indigo-500/30 shrink-0">
                                                <div className="absolute inset-0 bg-gradient-to-r from-indigo-600 to-violet-600 opacity-90 group-hover:opacity-100 transition-opacity"></div>
                                                <div className="relative flex items-center gap-2">
                                                    {warehouseLoading ? <Icon name="loader" className="animate-spin" /> : <Icon name="search" size={12} className="group-hover:rotate-12 transition-transform"/>}
                                                    <span>{warehouseLoading ? 'ĐANG TẢI...' : 'TRUY VẤN'}</span>
                                                </div>
                                            </button>
                                            <FilterToggleButton expanded={filtersExpanded} onToggle={() => setFiltersExpanded(v => !v)} count={warehouseRow2Count} />
                                            <ExportButton kind="warehouse" />
                                        </div>
                                    </div>
                                    {filtersExpanded && <div className="grid grid-cols-8 gap-1.5">
                                        <IssueReceiveDropdown value={warehouseFilters.issue_receive} onChange={v => setWarehouseFilters(p => ({...p, issue_receive: v}))} isActive={activeDropdown === 'issueReceive'} onToggle={setActiveDropdown}/>
                                        <PremiumDropdown label="Hàng hóa" items={meta.items} selectedItems={filters.item_ids} onSelect={id => toggleFilter('item_ids', id)} isActive={activeDropdown === 'Hàng hóa'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Sản phẩm" items={meta.products} selectedItems={filters.product_ids} onSelect={id => toggleFilter('product_ids', id)} isActive={activeDropdown === 'Sản phẩm'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Mục chi phí" items={meta.expenses} selectedItems={filters.expense_ids} onSelect={id => toggleFilter('expense_ids', id)} isActive={activeDropdown === 'Mục chi phí'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Công việc" items={meta.jobs} selectedItems={filters.job_ids} onSelect={id => toggleFilter('job_ids', id)} isActive={activeDropdown === 'Công việc'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Đối tượng" items={meta.pr_details} selectedItems={filters.pr_detail_ids} onSelect={id => toggleFilter('pr_detail_ids', id)} isActive={activeDropdown === 'Đối tượng'} onToggle={setActiveDropdown} />
                                        <PremiumDropdown label="Kho" items={meta.warehouses} selectedItems={warehouseFilters.wh_ids} onSelect={id => toggleWarehouseFilter('wh_ids', id)} isActive={activeDropdown === 'Kho'} onToggle={setActiveDropdown} align="right" />
                                        <div>
                                            <div className="label-text">Số chứng từ</div>
                                            <input type="text" value={warehouseFilters.tran_no_search} onChange={e => setWarehouseFilters(p => ({...p, tran_no_search: e.target.value}))} placeholder="Nhập số CT..." className="filter-control text-[11px] font-bold" />
                                        </div>
                                    </div>}
                                </div>
                            </div>
                            <div className="flex-1 min-h-0 p-3 overflow-hidden bg-slate-50 flex flex-col relative">
                                {warehouseLoading && <div className="absolute inset-0 bg-white/40 z-50 flex flex-col items-center justify-center backdrop-blur-[2px] transition-all"><div className="bg-white p-6 rounded-3xl shadow-2xl flex flex-col items-center gap-4 border border-indigo-50"><Icon name="loader" size={48} className="animate-spin text-indigo-600"/><div className="text-[10px] font-black text-indigo-600 uppercase tracking-widest animate-pulse">Đang truy vấn dữ liệu...</div></div></div>}
                                

                                <div className="bg-slate-100/80 border border-slate-200 rounded-xl p-2 mb-3 mx-6 mt-1 flex items-center gap-3 min-h-[44px] shadow-inner"
                                    onDragOver={e => e.preventDefault()}
                                    onDrop={e => {
                                        e.preventDefault();
                                        let col = e.dataTransfer.getData('text/plain');
                                        if (!col) col = e.dataTransfer.getData('col');
                                        if (col && !groupByWarehouse.includes(col)) setGroupByWarehouse([...groupByWarehouse, col]);
                                        
                                        const fromIdx = e.dataTransfer.getData('reorder');
                                        if (fromIdx !== '') {
                                            const arr = [...groupByWarehouse];
                                            const item = arr.splice(parseInt(fromIdx), 1)[0];
                                            arr.push(item);
                                            setGroupByWarehouse(arr);
                                        }
                                    }}
                                >
                                    <div className="bg-indigo-100 text-indigo-700 w-6 h-6 flex items-center justify-center rounded-lg shadow-sm">
                                        <Icon name="sliders" size={12}/>
                                    </div>
                                    <span className="text-[10px] text-slate-500 font-black uppercase tracking-widest">Khu vực gom nhóm:</span>
                                    {groupByWarehouse.length === 0 ? <span className="text-[10px] text-slate-400 italic">Kéo tiêu đề cột thả vào đây</span> : null}
                                    {groupByWarehouse.map((g, i) => (
                                        <div key={g} 
                                            draggable
                                            onDragStart={e => { e.stopPropagation(); e.dataTransfer.setData('reorder', i.toString()); }}
                                            onDragOver={e => e.preventDefault()}
                                            onDrop={e => {
                                                e.stopPropagation();
                                                e.preventDefault();
                                                const fromIdx = e.dataTransfer.getData('reorder');
                                                if (fromIdx !== '') {
                                                    const arr = [...groupByWarehouse];
                                                    const item = arr.splice(parseInt(fromIdx), 1)[0];
                                                    arr.splice(i, 0, item);
                                                    setGroupByWarehouse(arr);
                                                } else {
                                                    let col = e.dataTransfer.getData('text/plain');
                                                    if (!col) col = e.dataTransfer.getData('col');
                                                    if (col && !groupByWarehouse.includes(col)) {
                                                        const arr = [...groupByWarehouse];
                                                        arr.splice(i, 0, col);
                                                        setGroupByWarehouse(arr);
                                                    }
                                                }
                                            }}
                                            className="bg-white border border-indigo-200 text-indigo-700 px-3 py-1.5 rounded-full text-[10px] font-black flex items-center gap-2 shadow-sm animate-fade-in cursor-move">
                                            {g}
                                            <button onClick={() => setGroupByWarehouse(groupByWarehouse.filter(x => x !== g))} className="text-slate-300 hover:text-red-500 transition-colors bg-slate-50 hover:bg-red-50 rounded-full w-4 h-4 flex items-center justify-center"><Icon name="lock" size={8}/></button>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col mx-0">
                                    <div className="flex-1 min-h-0 overflow-auto custom-scrollbar" ref={warehouseScrollRef}>
                                        <table className="w-max border-collapse" style={{ width: 'max-content', minWidth: '100%' }}>
                                            <thead className="sticky top-0 bg-slate-50/95 backdrop-blur-md z-30 shadow-sm">
                                                <tr className="text-slate-400 uppercase text-[9px] font-black tracking-widest text-center">
                                                    <th className="border-r w-12">#</th>
                                                    <SortableHeader field="ISSUE_RECEIVE"        sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-14">N/X</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_ID"      sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-20">Mã ĐV</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_NAME"    sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-40 px-3" align="left">Tên đơn vị</SortableHeader>
                                                    <SortableHeader field="TRAN_ID"              sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-16">Mã CT</SortableHeader>
                                                    <SortableHeader field="TRAN_ID"              sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-40 px-3">Tên chứng từ</SortableHeader>
                                                    <SortableHeader field="TRAN_NO"              sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-32 px-3">Số CT</SortableHeader>
                                                    <SortableHeader field="TRAN_DATE"            sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24">Ngày CT</SortableHeader>
                                                    <SortableHeader field="WAREHOUSE_ID"         sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-20">Mã kho</SortableHeader>
                                                    <SortableHeader field="WAREHOUSE_NAME"       sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-36 px-3" align="left">Tên kho</SortableHeader>
                                                    <SortableHeader field="WAREHOUSE_ID_ISSUE"   sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-20">Mã kho xuất</SortableHeader>
                                                    <SortableHeader field="WAREHOUSE_NAME_ISSUE" sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-36 px-3" align="left">Tên kho xuất</SortableHeader>
                                                    <SortableHeader field="ITEM_ID"              sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24">Mã hàng</SortableHeader>
                                                    <SortableHeader field="ITEM_NAME"            sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-44 px-3" align="left">Tên hàng hóa</SortableHeader>
                                                    <SortableHeader field="UNIT_ID_WH"           sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-16">ĐVT</SortableHeader>
                                                    <SortableHeader field="QUANTITY"             sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24 px-2" align="right">Số lượng</SortableHeader>
                                                    <SortableHeader field="UNIT_ID_EXTRA"        sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-16">ĐVT QĐ</SortableHeader>
                                                    <SortableHeader field="QUANTITY_EXTRA"       sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24 px-2" align="right">SL QĐ</SortableHeader>
                                                    <SortableHeader field="UNIT_PRICE"           sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-28 px-2" align="right">Đơn giá</SortableHeader>
                                                    <SortableHeader field="AMOUNT"               sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-32 px-2" align="right">Thành tiền</SortableHeader>
                                                    <SortableHeader field="ACCOUNT_ID"           sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24">Tài khoản</SortableHeader>
                                                    <SortableHeader field="ACCOUNT_ID_CONTRA"    sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24">TK đối ứng</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID"         sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24">Mã ĐT</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_NAME"       sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-40 px-3" align="left">Tên đối tượng</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID"           sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24">Mã MCP</SortableHeader>
                                                    <SortableHeader field="EXPENSE_NAME"         sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-36 px-3" align="left">Tên MCP</SortableHeader>
                                                    <SortableHeader field="JOB_ID"               sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="border-r w-24">Mã CV</SortableHeader>
                                                    <SortableHeader field="JOB_NAME"             sort={warehouseSort} onSort={f => setWarehouseSort(s => cycleSort(s, f))} className="w-36 px-3" align="left">Tên công việc</SortableHeader>
                                                </tr>
                                                <tr className="bg-indigo-50/60 border-b-2 border-indigo-200">
                                                    {['','','ORGANIZATION_ID','ORGANIZATION_NAME','TRAN_ID','TRAN_NAME','TRAN_NO','TRAN_DATE','WAREHOUSE_ID','WAREHOUSE_NAME','WAREHOUSE_ID_ISSUE','WAREHOUSE_NAME_ISSUE','ITEM_ID','ITEM_NAME','UNIT_ID_WH','','UNIT_ID_EXTRA','','','','ACCOUNT_ID','ACCOUNT_ID_CONTRA','PR_DETAIL_ID','PR_DETAIL_NAME','EXPENSE_ID','EXPENSE_NAME','JOB_ID','JOB_NAME'].map((key, idx) => (
                                                        <th key={idx} className="border-r px-1 py-1">
                                                            {key ? <input
                                                                type="text"
                                                                value={warehouseColSearch[key] || ''}
                                                                onChange={e => setWarehouseColSearch(p => ({...p, [key]: e.target.value}))}
                                                                className="w-full bg-white border border-slate-200 rounded-md px-1.5 py-1 text-[10px] font-semibold text-slate-700 outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-200 focus:bg-indigo-50/30 transition-all placeholder:text-slate-300 placeholder:text-center"
                                                            /> : null}
                                                        </th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody className="text-[11px] font-medium text-slate-700">
                                                {warehouseVS.topPadding > 0 && <tr><td colSpan={100} style={{ height: warehouseVS.topPadding, padding: 0, border: 0 }}></td></tr>}
                                                {warehouseFlatData.slice(warehouseVS.startIndex, warehouseVS.endIndex + 1).map((row, i) => (
                                                    row.isGroup ?
                                                    <WarehouseGroupRow key={row.id} node={row} toggleExpand={handleToggleWarehouseGroup} /> :
                                                    <WarehouseRow key={warehouseVS.startIndex + i} r={row} idx={warehouseVS.startIndex + i + 1} />
                                                ))}
                                                {warehouseVS.bottomPadding > 0 && <tr><td colSpan={100} style={{ height: warehouseVS.bottomPadding, padding: 0, border: 0 }}></td></tr>}
                                            </tbody>
                                            <tfoot className="sticky-footer">
                                                <tr className="text-slate-800 font-black text-[12px] bg-slate-50/95">
                                                    <td colSpan="15" className="border-r text-right px-4 py-3 uppercase text-[10px] text-slate-400">
                                                        Tổng toàn bộ truy vấn ({Number(warehousePagination.total_rows||0).toLocaleString()} dòng):
                                                    </td>
                                                    <td className="border-r text-right font-mono px-2 bg-slate-100/40">{Number(warehouseSummary.quantity||0).toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2})}</td>
                                                    <td className="border-r"></td>
                                                    <td className="border-r text-right font-mono px-2 bg-slate-100/40">{Number(warehouseSummary.quantity_extra||0).toLocaleString('en-US', {minimumFractionDigits:2,maximumFractionDigits:2})}</td>
                                                    <td className="border-r"></td>
                                                    <td className="border-r text-right font-mono px-2 text-emerald-700 bg-emerald-100/40">{Math.round(Number(warehouseSummary.amount||0)).toLocaleString('en-US')}</td>
                                                    <td colSpan="8"></td>
                                                </tr>
                                            </tfoot>
                                        </table>
                                    </div>
                                    <div className="p-4 bg-white border-t flex justify-between items-center px-10 shrink-0 z-40 shadow-inner">
                                        <div className="flex items-center gap-8">
                                            <div className="text-[10px] font-black text-slate-300 uppercase tracking-widest italic underline">iPOS Accounting Report</div>
                                        </div>
                                        <div className="flex items-center gap-6">
                                                <div className="flex items-center gap-2">
                                                    <button disabled={warehousePagination.page <= 1} onClick={() => loadWarehouseData(warehousePagination.page - 1)} className="page-btn w-10 h-10 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-left" size={18}/></button>
                                                    <div className="flex items-center gap-2 px-4 py-1 bg-slate-50 rounded-2xl border border-slate-100">
                                                        <span className="text-[10px] font-black text-slate-400">TRANG</span>
                                                        <input type="number" min="1" max={warehousePagination.total_pages} value={warehousePagination.page} onChange={e => { const val = parseInt(e.target.value); if (val >= 1 && val <= warehousePagination.total_pages) loadWarehouseData(val); }} className="w-12 bg-transparent text-center font-black text-indigo-600 outline-none" />
                                                        <span className="text-[10px] font-black text-slate-400">/ {warehousePagination.total_pages}</span>
                                                    </div>
                                                    <button disabled={warehousePagination.page >= warehousePagination.total_pages} onClick={() => loadWarehouseData(warehousePagination.page + 1)} className="page-btn w-10 h-10 rounded-full flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"><Icon name="chevron-right" size={18}/></button>
                                                </div>
                                            </div>
                                        <div className="flex flex-col items-end">
                                            <span className="text-[9px] font-black text-slate-300 uppercase tracking-tighter">Warehouse Detail View</span>
                                            <span className="text-[11px] font-black text-indigo-400 uppercase tracking-widest">
                                                {isWarehouseGroupedOrSearched ? `${warehouseData.length.toLocaleString()} dòng | Gom nhóm & tìm kiếm` : `Trang ${warehousePagination.page} / ${warehousePagination.total_pages}`}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}

                    {activeTab === 'report' && (
                        <div className="flex-1 flex flex-col relative overflow-hidden">
                            {loading && <div className="absolute inset-0 bg-white/60 z-50 flex flex-col items-center justify-center backdrop-blur-[4px] transition-all"><div className="bg-white p-8 rounded-[40px] shadow-[0_30px_100px_rgba(0,0,0,0.2)] flex flex-col items-center gap-6 border border-indigo-50 scale-110"><div className="relative"><div className="w-16 h-16 border-4 border-indigo-100 rounded-full"></div><div className="w-16 h-16 border-4 border-indigo-600 rounded-full border-t-transparent animate-spin absolute top-0 left-0"></div><Icon name="file-text" size={24} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-indigo-600"/></div><div className="flex flex-col items-center gap-1"><div className="text-[12px] font-black text-indigo-900 uppercase tracking-widest">Đang kết xuất báo cáo</div><div className="text-[9px] font-bold text-slate-400 uppercase tracking-tighter italic">Vui lòng chờ trong giây lát...</div></div></div></div>}
                            <ReportTab
                                filters={filters}
                                period={period}
                                setPeriod={setPeriod}
                                meta={meta}
                                onToggleFilter={toggleFilter}
                                activeDropdown={activeDropdown}
                                setActiveDropdown={setActiveDropdown}
                                reportData={reportData}
                                loadReportData={loadReportData}
                                loading={loading}
                                monthList={monthList}
                                monthlyData={monthlyData}
                                jobList={jobList}
                                jobData={jobData}
                                reportType={reportType}
                                setReportType={setReportType}
                                setPendingReportType={setPendingReportType}
                                setShowClearModal={setShowClearModal}
                                trialBalanceData={trialBalanceData}
                                trialBalanceTotal={trialBalanceTotal}
                            />
                        </div>
                    )}
                    {/* MODAL: Xác nhận xuất CSV cho dataset lớn */}
                    {exportConfirm && (
                        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-[9999] px-4 animate-backdrop">
                            <div className="bg-white rounded-3xl p-8 max-w-lg w-full shadow-2xl border border-slate-100 animate-modal">
                                <div className="flex items-start gap-4 mb-5">
                                    <div className="w-12 h-12 rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center shrink-0">
                                        <Icon name="file-spreadsheet" size={22} className="text-amber-600"/>
                                    </div>
                                    <div className="flex-1">
                                        <h2 className="text-[16px] font-black text-slate-900 tracking-tight">Xuất dữ liệu lớn</h2>
                                        <p className="text-[11px] font-bold text-slate-400 mt-0.5">Tập dữ liệu vượt ngưỡng xử lý browser</p>
                                    </div>
                                </div>
                                <div className="bg-slate-50 rounded-2xl px-4 py-3 mb-5 border border-slate-100">
                                    <div className="flex items-center justify-between mb-1.5">
                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Số dòng</span>
                                        <span className="text-[15px] font-black text-indigo-600 tabular-nums">{exportConfirm.total.toLocaleString()}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Định dạng</span>
                                        <span className="text-[12px] font-black text-emerald-700">CSV (UTF-8)</span>
                                    </div>
                                </div>
                                <div className="text-[12px] text-slate-600 leading-relaxed mb-6">
                                    File CSV sẽ được tạo trên máy server, lưu vào folder <code className="px-1.5 py-0.5 bg-slate-100 rounded text-[11px] font-mono text-slate-800">Downloads\iPOS_Accounting_Report\</code> và có thể mở trực tiếp bằng Excel / LibreOffice.
                                </div>
                                <div className="flex gap-3">
                                    <button onClick={() => setExportConfirm(null)}
                                            className="flex-1 px-5 py-3 rounded-2xl border border-slate-200 text-slate-600 font-black text-[11px] hover:bg-slate-50 transition-all uppercase tracking-widest">
                                        Hủy
                                    </button>
                                    <button onClick={() => startServerExport(exportConfirm.kind, exportConfirm.total)}
                                            className="flex-1 px-5 py-3 rounded-2xl bg-indigo-600 text-white font-black text-[11px] hover:bg-indigo-700 shadow-xl shadow-indigo-200 transition-all uppercase tracking-widest flex items-center justify-center gap-2">
                                        <Icon name="check" size={12}/> Xác nhận
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* MODAL: Tải xong → Mở file / Mở folder */}
                    {exportDone && (
                        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-[9999] px-4 animate-backdrop">
                            <div className="bg-white rounded-3xl p-8 max-w-lg w-full shadow-2xl border border-slate-100 animate-modal">
                                <div className="flex items-start gap-4 mb-5">
                                    <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center shrink-0">
                                        <Icon name="check" size={22} className="text-emerald-600"/>
                                    </div>
                                    <div className="flex-1">
                                        <h2 className="text-[16px] font-black text-slate-900 tracking-tight">Đã xuất xong</h2>
                                        <p className="text-[11px] font-bold text-slate-400 mt-0.5">
                                            {(exportDone.total || 0).toLocaleString()} dòng · {exportDone.filename}
                                        </p>
                                    </div>
                                </div>
                                <div className="bg-slate-50 rounded-2xl px-4 py-3 mb-5 border border-slate-100">
                                    <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1.5">Đường dẫn</div>
                                    <div className="text-[11px] font-mono text-slate-700 break-all leading-relaxed">{exportDone.file_path}</div>
                                </div>
                                <div className="flex gap-3">
                                    <button onClick={() => setExportDone(null)}
                                            className="px-5 py-3 rounded-2xl border border-slate-200 text-slate-600 font-black text-[11px] hover:bg-slate-50 transition-all uppercase tracking-widest">
                                        Đóng
                                    </button>
                                    <button onClick={() => openExportedFolder(exportDone.file_path)}
                                            className="flex-1 px-5 py-3 rounded-2xl border-2 border-indigo-200 text-indigo-700 bg-indigo-50 font-black text-[11px] hover:bg-indigo-100 transition-all uppercase tracking-widest flex items-center justify-center gap-2">
                                        <Icon name="file-text" size={12}/> Mở folder
                                    </button>
                                    <button onClick={() => openExportedFile(exportDone.file_path)}
                                            className="flex-1 px-5 py-3 rounded-2xl bg-emerald-600 text-white font-black text-[11px] hover:bg-emerald-700 shadow-xl shadow-emerald-200 transition-all uppercase tracking-widest flex items-center justify-center gap-2">
                                        <Icon name="file-spreadsheet" size={12}/> Mở file
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {exporting && exportProgress && (
                        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-[9999] px-4">
                            <div className="bg-white rounded-3xl p-8 max-w-md w-full shadow-2xl border border-slate-100">
                                <div className="flex items-center gap-4 mb-6">
                                    <div className="relative shrink-0">
                                        <div className="w-12 h-12 border-4 border-emerald-100 rounded-full"></div>
                                        <div className="w-12 h-12 border-4 border-emerald-600 rounded-full border-t-transparent animate-spin absolute top-0 left-0"></div>
                                    </div>
                                    <div>
                                        <div className="text-[15px] font-black text-slate-900 uppercase tracking-tight">Đang xuất Excel</div>
                                        <div className="text-[11px] font-bold text-slate-400 mt-0.5">
                                            {exportProgress.phase === 'fetch'  && 'Đang tải dữ liệu từ server...'}
                                            {exportProgress.phase === 'build'  && `Đang dựng file: ${exportProgress.current.toLocaleString()} / ${exportProgress.total.toLocaleString()} dòng`}
                                            {exportProgress.phase === 'write'  && 'Đang ghi file xlsx...'}
                                            {exportProgress.phase === 'stream' && `Đang stream ${exportProgress.total.toLocaleString()} dòng → browser tải file CSV trực tiếp`}
                                        </div>
                                    </div>
                                </div>
                                {exportProgress.total > 0 && (
                                    <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                                        <div className="h-full bg-gradient-to-r from-emerald-500 to-emerald-600 transition-all"
                                             style={{ width: `${Math.min(100, Math.round((exportProgress.current / Math.max(1, exportProgress.total)) * 100))}%` }}></div>
                                    </div>
                                )}
                                <div className="text-[10px] font-bold text-slate-400 mt-3 text-center">
                                    Vui lòng không tắt cửa sổ. Dữ liệu lớn có thể mất vài phút.
                                </div>
                            </div>
                        </div>
                    )}
                    {showClearModal && (
                        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-[9999] animate-backdrop px-4">
                            <div className="bg-white/90 backdrop-blur-xl rounded-[32px] p-10 max-w-md w-full shadow-[0_32px_100px_rgba(0,0,0,0.3)] border border-white animate-modal">
                                <h2 className="text-2xl font-black text-slate-900 mb-2 tracking-tight">Chuyển mẫu báo cáo?</h2>
                                <p className="text-slate-500 font-medium mb-8 text-[13px] leading-relaxed">Nội dung báo cáo hiện tại sẽ bị xóa. Bạn cần phải tải lại báo cáo nếu muốn quay lại mẫu cũ.</p>
                                <div className="flex gap-4">
                                    <button onClick={() => setShowClearModal(false)} className="flex-1 px-6 py-3.5 rounded-2xl border border-slate-200 text-slate-600 font-black text-[11px] hover:bg-slate-50 transition-all uppercase tracking-widest">Hủy</button>
                                    <button onClick={() => { setReportType(pendingReportType); setReportData({}); setMonthList([]); setMonthlyData({}); setJobList([]); setJobData({}); setShowClearModal(false); }} className="flex-1 px-6 py-3.5 rounded-2xl bg-indigo-600 text-white font-black text-[11px] hover:bg-indigo-700 shadow-xl shadow-indigo-200 transition-all uppercase tracking-widest">Xác nhận</button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            );
        };
        ReactDOM.createRoot(document.getElementById('root')).render(<App />);
    