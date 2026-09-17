# -*- coding: utf-8 -*-
import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Add metaMaps to App
old_meta = 'const [meta, setMeta] = useState({ accounts: [], orgs: [], pr_details: [], tran_ids: [], jobs: [], items: [], products: [], expenses: [], warehouses: [], db_info: {}, global_total: 0 });\n            const [loading, setLoading] = useState(false);\n            const [loginLoading, setLoginLoading] = useState(false);\n            const [loginError, setLoginError] = useState("");'
new_meta = old_meta + '''
            const metaMaps = useMemo(() => {
                const mapOf = (arr) => arr.reduce((acc, curr) => { acc[curr.id] = curr.name; return acc; }, {});
                return {
                    prMap: mapOf(meta.pr_details || []),
                    expMap: mapOf(meta.expenses || []),
                    jobMap: mapOf(meta.jobs || []),
                    itemMap: mapOf(meta.items || []),
                    productMap: mapOf(meta.products || []),
                    orgMap: mapOf(meta.orgs || [])
                };
            }, [meta]);'''
html = html.replace(old_meta, new_meta)

# 2. Update LedgerRow definition
old_ledger_row = '''const LedgerRow = memo(({ r, idx, pageSize }) => (
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
                <td className="border-r text-center italic">{r.EXPENSE_ID}</td>
                <td className="border-r whitespace-nowrap italic px-4">{r.EXPENSE_NAME}</td>
                <td className="border-r text-center italic">{r.ORGANIZATION_ID}</td>
                <td className="border-r whitespace-nowrap px-4 font-bold">{r.ORGANIZATION_NAME}</td>
                <td className="border-r text-center italic">{r.ITEM_ID}</td>
                <td className="border-r px-4 whitespace-nowrap italic">{r.ITEM_NAME}</td>
                <td className="border-r text-center italic">{r.JOB_ID}</td>
                <td className="border-r text-center italic">{r.PRODUCT_ID}</td>
                <td className="px-4 whitespace-nowrap italic">{r.PRODUCT_NAME}</td>
            </tr>
        ));'''
new_ledger_row = '''const LedgerRow = memo(({ r, idx, pageSize, metaMaps }) => (
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
                <td className="border-r whitespace-nowrap italic px-3 text-slate-600 max-w-[200px] truncate" title={r.PR_DETAIL_NAME || metaMaps?.prMap?.[r.PR_DETAIL_ID] || ''}>{r.PR_DETAIL_NAME || metaMaps?.prMap?.[r.PR_DETAIL_ID] || ''}</td>
                <td className="border-r text-center italic">{r.PR_DETAIL_ID_CONTRA}</td>
                <td className="border-r whitespace-nowrap italic px-3 text-slate-600 max-w-[200px] truncate" title={r.PR_DETAIL_NAME_CONTRA || metaMaps?.prMap?.[r.PR_DETAIL_ID_CONTRA] || ''}>{r.PR_DETAIL_NAME_CONTRA || metaMaps?.prMap?.[r.PR_DETAIL_ID_CONTRA] || ''}</td>
                <td className="border-r text-center italic">{r.EXPENSE_ID}</td>
                <td className="border-r whitespace-nowrap italic px-4 text-slate-600 max-w-[200px] truncate" title={r.EXPENSE_NAME || metaMaps?.expMap?.[r.EXPENSE_ID] || ''}>{r.EXPENSE_NAME || metaMaps?.expMap?.[r.EXPENSE_ID] || ''}</td>
                <td className="border-r text-center italic">{r.EXPENSE_ID_CONTRA}</td>
                <td className="border-r whitespace-nowrap italic px-4 text-slate-600 max-w-[200px] truncate" title={r.EXPENSE_NAME_CONTRA || metaMaps?.expMap?.[r.EXPENSE_ID_CONTRA] || ''}>{r.EXPENSE_NAME_CONTRA || metaMaps?.expMap?.[r.EXPENSE_ID_CONTRA] || ''}</td>
                <td className="border-r text-center italic">{r.JOB_ID}</td>
                <td className="border-r whitespace-nowrap italic px-3 text-slate-600 max-w-[200px] truncate" title={r.JOB_NAME || metaMaps?.jobMap?.[r.JOB_ID] || ''}>{r.JOB_NAME || metaMaps?.jobMap?.[r.JOB_ID] || ''}</td>
                <td className="border-r text-center italic">{r.JOB_ID_CONTRA}</td>
                <td className="border-r whitespace-nowrap italic px-3 text-slate-600 max-w-[200px] truncate" title={r.JOB_NAME_CONTRA || metaMaps?.jobMap?.[r.JOB_ID_CONTRA] || ''}>{r.JOB_NAME_CONTRA || metaMaps?.jobMap?.[r.JOB_ID_CONTRA] || ''}</td>
                <td className="border-r text-center italic">{r.ORGANIZATION_ID}</td>
                <td className="border-r whitespace-nowrap px-4 font-bold max-w-[200px] truncate" title={r.ORGANIZATION_NAME || metaMaps?.orgMap?.[r.ORGANIZATION_ID] || ''}>{r.ORGANIZATION_NAME || metaMaps?.orgMap?.[r.ORGANIZATION_ID] || ''}</td>
                <td className="border-r text-center italic">{r.ITEM_ID}</td>
                <td className="border-r px-4 whitespace-nowrap italic text-slate-600 max-w-[200px] truncate" title={r.ITEM_NAME || metaMaps?.itemMap?.[r.ITEM_ID] || ''}>{r.ITEM_NAME || metaMaps?.itemMap?.[r.ITEM_ID] || ''}</td>
                <td className="border-r text-center italic">{r.ITEM_ID_CONTRA}</td>
                <td className="border-r px-4 whitespace-nowrap italic text-slate-600 max-w-[200px] truncate" title={r.ITEM_NAME_CONTRA || metaMaps?.itemMap?.[r.ITEM_ID_CONTRA] || ''}>{r.ITEM_NAME_CONTRA || metaMaps?.itemMap?.[r.ITEM_ID_CONTRA] || ''}</td>
                <td className="border-r text-center italic">{r.PRODUCT_ID}</td>
                <td className="border-r px-4 whitespace-nowrap italic text-slate-600 max-w-[200px] truncate" title={r.PRODUCT_NAME || metaMaps?.productMap?.[r.PRODUCT_ID] || ''}>{r.PRODUCT_NAME || metaMaps?.productMap?.[r.PRODUCT_ID] || ''}</td>
                <td className="border-r text-center italic">{r.PRODUCT_ID_CONTRA}</td>
                <td className="px-4 whitespace-nowrap italic text-slate-600 max-w-[200px] truncate" title={r.PRODUCT_NAME_CONTRA || metaMaps?.productMap?.[r.PRODUCT_ID_CONTRA] || ''}>{r.PRODUCT_NAME_CONTRA || metaMaps?.productMap?.[r.PRODUCT_ID_CONTRA] || ''}</td>
            </tr>
        ));'''
html = html.replace(old_ledger_row, new_ledger_row)

# 3. Update the LedgerRow component call
html = html.replace('<LedgerRow key={i} idx={idx} r={r} pageSize={filters.page_size} />', '<LedgerRow key={i} idx={idx} r={r} pageSize={filters.page_size} metaMaps={metaMaps} />')

# 4. Update LEDGER_EXPORT_COLS
old_ledger_export = "const LEDGER_EXPORT_COLS = [\n                ['TRAN_DATE','Ngày CT'],['TRAN_NO','S? ch?ng t?'],['TRAN_ID','Mã CT'],['TRAN_NAME','Tên ch?ng t?'],\n                ['ACCOUNT_ID','Tài kho?n'],['ACCOUNT_ID_CONTRA','Ð?i ?ng'],\n                ['DESCRIPTION','Di?n gi?i'],\n                ['DEBIT','N?'],['CREDIT','Có'],\n                ['PR_DETAIL_NAME','Ð?i tu?ng'],['EXPENSE_NAME','M?c chi phí'],\n                ['ORGANIZATION_ID','Mã ÐV'],['ORGANIZATION_NAME','Tên don v?'],\n                ['ITEM_NAME','Hàng hóa'],['PRODUCT_NAME','S?n ph?m']\n            ];"
new_ledger_export = "const LEDGER_EXPORT_COLS = [\n                ['TRAN_DATE','Ngày CT'],['TRAN_NO','S? ch?ng t?'],['TRAN_ID','Mã CT'],['TRAN_NAME','Tên ch?ng t?'],\n                ['ACCOUNT_ID','Tài kho?n'],['ACCOUNT_ID_CONTRA','Ð?i ?ng'],\n                ['DESCRIPTION','Di?n gi?i'],\n                ['DEBIT','N?'],['CREDIT','Có'],\n                ['PR_DETAIL_ID','Mã d?i tu?ng'],['PR_DETAIL_NAME','Tên d?i tu?ng'],['PR_DETAIL_ID_CONTRA','Mã ÐT d?i ?ng'],['PR_DETAIL_NAME_CONTRA','Tên ÐT d?i ?ng'],\n                ['EXPENSE_ID','Mã m?c chi phí'],['EXPENSE_NAME','Tên m?c chi phí'],['EXPENSE_ID_CONTRA','Mã MCP d?i ?ng'],['EXPENSE_NAME_CONTRA','Tên MCP d?i ?ng'],\n                ['JOB_ID','Mã công vi?c'],['JOB_NAME','Tên công vi?c'],['JOB_ID_CONTRA','Mã CV d?i ?ng'],['JOB_NAME_CONTRA','Tên CV d?i ?ng'],\n                ['ORGANIZATION_ID','Mã ÐV'],['ORGANIZATION_NAME','Tên don v?'],\n                ['ITEM_ID','Mã hàng'],['ITEM_NAME','Tên hàng hóa'],['ITEM_ID_CONTRA','Mã hàng d?i ?ng'],['ITEM_NAME_CONTRA','Tên hàng d?i ?ng'],\n                ['PRODUCT_ID','Mã s?n ph?m'],['PRODUCT_NAME','Tên s?n ph?m'],['PRODUCT_ID_CONTRA','Mã SP d?i ?ng'],['PRODUCT_NAME_CONTRA','Tên SP d?i ?ng']\n            ];"
html = html.replace(old_ledger_export, new_ledger_export)

# 5. Update extractLedgerRow
old_extract = "const extractLedgerRow = (r) => LEDGER_EXPORT_COLS.map(([key]) => {\n                if (key === 'DEBIT')  return r.DEBIT_CREDIT === 'DEB' ? Number(r.AMOUNT || 0) : '';\n                if (key === 'CREDIT') return r.DEBIT_CREDIT === 'CRD' ? Number(r.AMOUNT || 0) : '';\n                const v = r[key];\n                return v == null ? '' : v;\n            });"
new_extract = "const extractLedgerRow = (r) => LEDGER_EXPORT_COLS.map(([key]) => {\n                if (key === 'DEBIT')  return r.DEBIT_CREDIT === 'DEB' ? Number(r.AMOUNT || 0) : '';\n                if (key === 'CREDIT') return r.DEBIT_CREDIT === 'CRD' ? Number(r.AMOUNT || 0) : '';\n                if (key === 'PR_DETAIL_NAME') return r.PR_DETAIL_NAME || metaMaps?.prMap?.[r.PR_DETAIL_ID] || '';\n                if (key === 'PR_DETAIL_NAME_CONTRA') return r.PR_DETAIL_NAME_CONTRA || metaMaps?.prMap?.[r.PR_DETAIL_ID_CONTRA] || '';\n                if (key === 'EXPENSE_NAME') return r.EXPENSE_NAME || metaMaps?.expMap?.[r.EXPENSE_ID] || '';\n                if (key === 'EXPENSE_NAME_CONTRA') return r.EXPENSE_NAME_CONTRA || metaMaps?.expMap?.[r.EXPENSE_ID_CONTRA] || '';\n                if (key === 'JOB_NAME') return r.JOB_NAME || metaMaps?.jobMap?.[r.JOB_ID] || '';\n                if (key === 'JOB_NAME_CONTRA') return r.JOB_NAME_CONTRA || metaMaps?.jobMap?.[r.JOB_ID_CONTRA] || '';\n                if (key === 'ORGANIZATION_NAME') return r.ORGANIZATION_NAME || metaMaps?.orgMap?.[r.ORGANIZATION_ID] || '';\n                if (key === 'ITEM_NAME') return r.ITEM_NAME || metaMaps?.itemMap?.[r.ITEM_ID] || '';\n                if (key === 'ITEM_NAME_CONTRA') return r.ITEM_NAME_CONTRA || metaMaps?.itemMap?.[r.ITEM_ID_CONTRA] || '';\n                if (key === 'PRODUCT_NAME') return r.PRODUCT_NAME || metaMaps?.productMap?.[r.PRODUCT_ID] || '';\n                if (key === 'PRODUCT_NAME_CONTRA') return r.PRODUCT_NAME_CONTRA || metaMaps?.productMap?.[r.PRODUCT_ID_CONTRA] || '';\n                const v = r[key];\n                return v == null ? '' : v;\n            });"
html = html.replace(old_extract, new_extract)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
# -*- coding: utf-8 -*-

