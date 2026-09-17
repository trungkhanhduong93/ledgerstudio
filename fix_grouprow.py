import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILE_PATH = r"d:\IACC HCM\iPOS ACC\ACC PMKT\LedgerReport\index.html"
with open(FILE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

group_rows_code = """
        const LedgerGroupRow = ({ node, toggleExpand }) => {
            return (
                <tr className={`border-b border-slate-200 font-bold text-[11px] cursor-pointer transition-colors ${node.level === 0 ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'bg-indigo-50 text-indigo-900 hover:bg-indigo-100'}`} onClick={() => toggleExpand(node.id)}>
                    <td colSpan={10} className="px-4 py-1.5 border-r border-indigo-200/30 whitespace-nowrap">
                        <div className="flex items-center gap-2" style={{ paddingLeft: `${node.level * 20}px` }}>
                            <span className={`inline-flex items-center justify-center w-3 h-3 border rounded-sm font-mono text-[9px] leading-none ${node.level === 0 ? 'border-indigo-400 bg-indigo-500' : 'border-indigo-300 bg-white'}`}>
                                {node.expanded ? '-' : '+'}
                            </span>
                            <span>{node.col}: {node.name}</span>
                            <span className={`text-[10px] ml-2 ${node.level === 0 ? 'text-indigo-200' : 'text-indigo-400'}`}>({node.children ? node.children.length : 0} dòng)</span>
                        </div>
                    </td>
                    <td className={`border-r border-indigo-200/30 text-right font-mono px-2 ${node.level === 0 ? 'text-white' : 'text-indigo-700'}`}>
                        {node.sums.DEBIT !== undefined && node.sums.DEBIT !== 0 ? node.sums.DEBIT.toLocaleString('en-US', {minimumFractionDigits:2}) : ''}
                    </td>
                    <td className={`border-r border-indigo-200/30 text-right font-mono px-2 ${node.level === 0 ? 'text-white' : 'text-indigo-700'}`}>
                        {node.sums.CREDIT !== undefined && node.sums.CREDIT !== 0 ? node.sums.CREDIT.toLocaleString('en-US', {minimumFractionDigits:2}) : ''}
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
                        {node.sums.TOTAL_AMOUNT !== undefined && node.sums.TOTAL_AMOUNT !== 0 ? node.sums.TOTAL_AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0}) : ''}
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
                        {node.sums.AMOUNT !== undefined && node.sums.AMOUNT !== 0 ? node.sums.AMOUNT.toLocaleString('en-US', {minimumFractionDigits:0}) : ''}
                    </td>
                    <td colSpan={100}></td>
                </tr>
            );
        };
"""

# Replace generic GroupRow
pattern = r'const GroupRow = \(\{ node, toggleExpand \}\) => \{[\s\S]*?return \([\s\S]*?</tr>\s*\);\s*\};'
html = re.sub(pattern, group_rows_code.strip(), html)

# Replace references
html = html.replace("<GroupRow key={row.id} node={row} toggleExpand={handleToggleLedgerGroup} />", "<LedgerGroupRow key={row.id} node={row} toggleExpand={handleToggleLedgerGroup} />")
html = html.replace("<GroupRow key={row.id} node={row} toggleExpand={handleTogglePurchaseGroup} />", "<PurchaseGroupRow key={row.id} node={row} toggleExpand={handleTogglePurchaseGroup} />")
html = html.replace("<GroupRow key={row.id} node={row} toggleExpand={handleToggleWarehouseGroup} />", "<WarehouseGroupRow key={row.id} node={row} toggleExpand={handleToggleWarehouseGroup} />")

with open(FILE_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print("Updated GroupRows successfully!")
