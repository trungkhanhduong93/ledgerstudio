# -*- coding: utf-8 -*-
import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 6. Update SortableHeaders
old_headers = '''                                                    <SortableHeader field="DEBIT_CREDIT"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-20 px-2">Phát sinh</SortableHeader>
                                                    <SortableHeader field="AMOUNT"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-32 px-4" align="right">Ghi N?</SortableHeader>
                                                    <SortableHeader field="AMOUNT"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-32 px-4" align="right">Ghi Có</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã ÐT</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_NAME"    sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-3" align="left">Ð?i tu?ng</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã MCP</SortableHeader>
                                                    <SortableHeader field="EXPENSE_NAME"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-36 px-4" align="left">M?c chi phí</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_ID"   sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã ÐV</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_NAME" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-4" align="left">Ðon v?</SortableHeader>
                                                    <SortableHeader field="ITEM_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã hàng</SortableHeader>
                                                    <SortableHeader field="ITEM_NAME"         sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-4" align="left">Hàng hóa</SortableHeader>
                                                    <SortableHeader field="JOB_ID"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã CV</SortableHeader>
                                                    <SortableHeader field="PRODUCT_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã SP</SortableHeader>
                                                    <SortableHeader field="PRODUCT_NAME"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="w-44 px-4" align="left">S?n ph?m</SortableHeader>'''
new_headers = '''                                                    <SortableHeader field="DEBIT_CREDIT"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-20 px-2">Phát sinh</SortableHeader>
                                                    <SortableHeader field="AMOUNT"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-32 px-4" align="right">Ghi N?</SortableHeader>
                                                    <SortableHeader field="AMOUNT"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-32 px-4" align="right">Ghi Có</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã d?i tu?ng</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_NAME"    sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-3" align="left">Tên d?i tu?ng</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã ÐT d?i ?ng</SortableHeader>
                                                    <SortableHeader field="PR_DETAIL_NAME_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-3" align="left">Tên ÐT d?i ?ng</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã m?c chi phí</SortableHeader>
                                                    <SortableHeader field="EXPENSE_NAME"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-36 px-4" align="left">Tên m?c chi phí</SortableHeader>
                                                    <SortableHeader field="EXPENSE_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã MCP d?i ?ng</SortableHeader>
                                                    <SortableHeader field="EXPENSE_NAME_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-36 px-4" align="left">Tên MCP d?i ?ng</SortableHeader>
                                                    <SortableHeader field="JOB_ID"            sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã công vi?c</SortableHeader>
                                                    <SortableHeader field="JOB_NAME"          sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-36 px-3" align="left">Tên công vi?c</SortableHeader>
                                                    <SortableHeader field="JOB_ID_CONTRA"     sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã CV d?i ?ng</SortableHeader>
                                                    <SortableHeader field="JOB_NAME_CONTRA"   sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-36 px-3" align="left">Tên CV d?i ?ng</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_ID"   sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã ÐV</SortableHeader>
                                                    <SortableHeader field="ORGANIZATION_NAME" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-4" align="left">Tên don v?</SortableHeader>
                                                    <SortableHeader field="ITEM_ID"           sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã hàng</SortableHeader>
                                                    <SortableHeader field="ITEM_NAME"         sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-4" align="left">Tên hàng hóa</SortableHeader>
                                                    <SortableHeader field="ITEM_ID_CONTRA"    sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã hàng d?i ?ng</SortableHeader>
                                                    <SortableHeader field="ITEM_NAME_CONTRA"  sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-40 px-4" align="left">Tên hàng d?i ?ng</SortableHeader>
                                                    <SortableHeader field="PRODUCT_ID"        sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã SP</SortableHeader>
                                                    <SortableHeader field="PRODUCT_NAME"      sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-44 px-4" align="left">Tên s?n ph?m</SortableHeader>
                                                    <SortableHeader field="PRODUCT_ID_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="border-r w-24">Mã SP d?i ?ng</SortableHeader>
                                                    <SortableHeader field="PRODUCT_NAME_CONTRA" sort={ledgerSort} onSort={f => setLedgerSort(s => cycleSort(s, f))} className="w-44 px-4" align="left">Tên SP d?i ?ng</SortableHeader>'''
html = html.replace(old_headers, new_headers)

# 7. Update column search inputs
old_inputs = "{['','TRAN_DATE','TRAN_NO','TRAN_ID','TRAN_NAME','ACCOUNT_ID','ACCOUNT_ID_CONTRA','DESCRIPTION','','','PR_DETAIL_ID','PR_DETAIL_NAME','EXPENSE_ID','EXPENSE_NAME','ORGANIZATION_ID','ORGANIZATION_NAME','ITEM_ID','ITEM_NAME','JOB_ID','PRODUCT_ID','PRODUCT_NAME'].map((key, idx) => ("
new_inputs = "{['','TRAN_DATE','TRAN_NO','TRAN_ID','TRAN_NAME','ACCOUNT_ID','ACCOUNT_ID_CONTRA','DESCRIPTION','','','PR_DETAIL_ID','PR_DETAIL_NAME','PR_DETAIL_ID_CONTRA','PR_DETAIL_NAME_CONTRA','EXPENSE_ID','EXPENSE_NAME','EXPENSE_ID_CONTRA','EXPENSE_NAME_CONTRA','JOB_ID','JOB_NAME','JOB_ID_CONTRA','JOB_NAME_CONTRA','ORGANIZATION_ID','ORGANIZATION_NAME','ITEM_ID','ITEM_NAME','ITEM_ID_CONTRA','ITEM_NAME_CONTRA','PRODUCT_ID','PRODUCT_NAME','PRODUCT_ID_CONTRA','PRODUCT_NAME_CONTRA'].map((key, idx) => ("
html = html.replace(old_inputs, new_inputs)


with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
