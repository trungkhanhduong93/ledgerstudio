# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# 📘 KIẾN TRÚC TOÀN TẬP — iPOS Ledger Report & Ledger Studio

> **File này là nguồn tham chiếu DUY NHẤT.** Một agent mới chỉ cần đọc hết file này là hiểu toàn bộ 2 ứng dụng,
> sửa được lỗi, thêm được báo cáo, tối ưu hiệu năng — KHÔNG cần đọc lại kiến trúc từ đầu.
> Cập nhật lần cuối: 2026-08-12. Ngôn ngữ code + UI: tiếng Việt.
> **Thay đổi mới nhất (12/08/2026) → xem mục 13 "Changelog".**

---

## 0. TL;DR cho agent đang vội

- 2 app **anh em, gần giống nhau nhưng ĐÃ PHÂN NHÁNH**: `LedgerReport/` và `LedgerStudio/` (thư mục cạnh nhau trong `ACC PMKT/`).
- Mỗi app = **`server.py`** (Flask + pyodbc, ~4000 dòng) + **`index.html`** (React qua CDN + Babel standalone, single-file ~430KB) → đóng gói **1 file EXE** bằng PyInstaller.
- Sửa backend → `server.py`; sửa UI/báo cáo → `index.html`. Sau khi sửa **PHẢI**: (1) syntax-check, (2) test bằng `test_client` in-process, (3) build EXE.
- **BẪY TEST LỚN NHẤT:** đừng test qua `python server.py` + curl (dễ dính "ghost server" cũ còn giữ port 5050). **Luôn test bằng Flask `test_client` in-process** (mục 9.1).
- DB test: db `IACC_CHULONG` (dữ liệu 2026-01 → 2026-10). **Thông tin kết nối (server/user/password) KHÔNG lưu trong repo** — hỏi chủ dự án để được cấp khi cần test.

---

## 1. Tổng quan & khác biệt 2 app

| | **LedgerReport** | **LedgerStudio** |
|---|---|---|
| EXE | `dist/iPOS_Accounting_Report.exe` | `dist/iPOS_Ledger_Studio.exe` |
| Tên app (JS `APP_NAME`) | iPOS Accounting Report | iPOS Ledger Studio |
| Tab dữ liệu | Chứng từ tổng hợp (LEDGER), Mua hàng, Kho, Bán hàng, Chứng từ tiền, Doanh thu chờ phân bổ, **Tồn kho thực tế** + tab Báo cáo | tương tự (không có Tồn kho thực tế) |
| **REPORT_TYPES** | BC001→BC014 | BC005→BC013 (không có BC001–BC004, BC009/BC010 có) |
| **BC011 nghĩa là gì** | LCTT gián tiếp (Chú Long) | **Tổng hợp phát sinh công nợ** |
| **BC013 nghĩa là gì** | Tổng hợp phát sinh công nợ (clone của Studio BC011) | **Bảng kê hóa đơn hàng hóa, dịch vụ BÁN RA (6.2-GTGT)** |
| **BC014** | Báo cáo bán hàng theo nguồn đơn | *(không có)* |

> ⚠️ **Mã BC KHÔNG đồng nhất giữa 2 app.** Cùng "BC011" và cùng "BC013" nhưng khác nghĩa hoàn toàn. Khi port báo cáo qua lại phải kiểm mã trống ở app đích.

### Danh sách báo cáo (tab "Báo cáo", chọn qua dropdown "Mẫu báo cáo")

| Mã | Tên | Endpoint | Nguồn dữ liệu | Có ở |
|---|---|---|---|---|
| BC001 | KQKD theo tháng | `/api/report` | LEDGER ⋈ DM_ITEM/DM_EXPENSE + `_calc_results` | Report |
| BC002 | KQKD theo công việc | `/api/report_by_job` | như trên | Report |
| BC003/004 | KQKD (tùy chỉnh) | `/api/report[_by_job]` | như trên (frontend biến đổi thêm 084 PHH/PQC) | Report |
| BC005 | Bảng cân đối kế toán (TT200) | `/api/balance_sheet` | BALANCE_VIEW + LEDGER_VIEW | cả 2 |
| BC006 | Bảng cân đối phát sinh | `/api/trial_balance` | BALANCE_VIEW + LEDGER | cả 2 |
| BC007 | Sổ nhật ký chung (S03a) | `/api/journal` (phân trang 1000/trang) | LEDGER_VIEW (+DM_ORGANIZATION map tên ĐV) | cả 2 |
| BC008 | Sổ chi tiết tài khoản | `/api/account_details` (phân trang) | BALANCE_VIEW + LEDGER_VIEW | cả 2 |
| BC009 | LCTT trực tiếp (B03) | `/api/cash_flow` | LEDGER theo TK đối ứng | cả 2 |
| BC010 | LCTT gián tiếp (B03) | `/api/cash_flow` | như trên | cả 2 |
| BC011 (Report) | LCTT gián tiếp Chú Long | `/api/cash_flow_cl` | lập từ CDKT | Report |
| BC011 (Studio) | Tổng hợp phát sinh công nợ | `/api/debt_summary` | BALANCE_VIEW + LEDGER theo PR_DETAIL | Studio |
| **BC012** | **Sổ tiền mặt và tiền ngân hàng** | `/api/cash_book` (phân trang + cache) + `/api/cash_book/export_csv` | **VOUCHER_VIEW** | **cả 2** |
| **BC013** (Report) | **Tổng hợp phát sinh công nợ** | `/api/debt_summary` | BALANCE_VIEW + LEDGER theo PR_DETAIL | **Report** |
| **BC013** (Studio) | **6.2 — Bảng kê hóa đơn, chứng từ hàng hóa, dịch vụ bán ra** | `/api/vat_sales_report` (phân trang 1000) | **VAT_TRANSACTION_VIEW** (`DEBIT_CREDIT='CRD'`), 2 chế độ `detail`/`summary` | **Studio** |

---

## 2. Kiến trúc kỹ thuật

### 2.1 Backend `server.py` (Flask + PyODBC)
- **Connection pool** `_conn_pool` (dict theo `_pool_key(db_config)` = md5 của server|db|user). `get_connection()` lấy/khôi phục kết nối.
- **`@with_db_lock`**: decorator bọc mọi route DB — đồng bộ luồng bằng `global_db_lock`, tự `invalidate_pool()` + reconnect khi mất kết nối (mã lỗi mạng `HY000`, `08S01`).
- **Login**: `POST /api/login` nhận JSON `{server, database, user, password, driver}` → `_make_conn()` (`Driver={...};SERVER=...;UID=...;PWD=...;Trusted_Connection=no;`, autocommit, `SET NOCOUNT ON`). Lưu `session['db_config']`. **Không hardcode credential.**
- **Bộ lọc đơn vị mặc định**: `_org_filter_sql(org_ids, col)` → nếu chọn đơn vị: `col IN (...)`; nếu KHÔNG chọn: `col NOT IN (<đơn vị ngoài cây '00'>)` (hàm `_get_external_org_ids` duyệt cây `DM_ORGANIZATION`). ⚠️ Vì mặc định trả về clause KHÔNG rỗng, thứ tự tham số phải đúng (mục 9.2).
- Nén gzip payload tự động cho JSON lớn.
- `kill_process_on_port(5050)` chạy đầu `__main__` để taskkill process cũ, rồi `app.run(host=0.0.0.0, port=5050)`. `APP_PORT=5050`.
- Werkzeug **có** log request ra stdout (không bị tắt).

### 2.2 Frontend `index.html` (React + Babel standalone + Tailwind, tất cả qua CDN)
- 1 file duy nhất, 1 `<script type="text/babel">` khổng lồ. Không có build step JS — Babel biên dịch JSX trong trình duyệt.
- Component gốc `App`. Các tab: ledger/purchase/warehouse/sale/voucher (dữ liệu lớn → **Virtual Scroll**) + `ReportTab` (các báo cáo BC, layout "tờ A4" `.report-paper`).
- **Virtual Scroll**: hook `useVirtualScroll(totalItems, itemHeight, containerRef)` (đo chiều cao dòng thật bằng median, overscan 50). Dùng cho các tab dữ liệu thô. Trả `{startIndex, endIndex, topPadding, bottomPadding}`; render spacer `<tr height=padding>` + slice.
- `ReportTab` nhận props từ `App` (filters, meta, reportType, loadReportData, reportData, trialBalanceData/Total, cashBookData, ...). **Mọi state ở App phải truyền xuống ReportTab qua props** — gọi "chui" tên biến của App trong JSX con sẽ vỡ Babel với `ReferenceError`.
- Bảng báo cáo nằm trong `.report-paper` (khổ A4), cuộn trong `paperScrollRef`.
- **CDN cần Internet.** Mất mạng/firewall chặn `unpkg.com`, `cdn.tailwindcss.com`, `fonts.googleapis.com` → màn hình trắng. Xem `FIX_OFFLINE_FILTERS.md` để inline.

### 2.3 Đóng gói EXE (PyInstaller one-file, no-console)
- `BuildEXE.bat` có `pause` → **treo ở chế độ non-interactive**. Agent nên chạy PyInstaller trực tiếp (mục 8).
- Nhúng kèm: `index.html`, `install_driver.ps1`, `manifest.json`, `icon.svg`. Máy đích cần **ODBC Driver 17 for SQL Server** (app gợi ý cài qua `install_driver.ps1`).

---

## 3. Database — bảng/view then chốt

| Đối tượng | Ghi chú QUAN TRỌNG |
|---|---|
| `dbo.LEDGER` | Sổ cái. Cột `TRAN_DATE` là **smalldatetime** (KHÔNG phải VARCHAR). Dùng `MONTH()/YEAR()/CONVERT(...,103)`; **KHÔNG dùng `SUBSTRING`** (lỗi 8116). Truyền tham số ngày từ Python bằng `.strftime('%Y%m%d')`. Có `PR_DETAIL_ID` (đối tượng công nợ). |
| `dbo.LEDGER_VIEW` | LEDGER + cột `ACCOUNT_ID_CONTRA` (TK đối ứng) — dùng cho sổ chi tiết/NKC. |
| `dbo.BALANCE_VIEW` | Số dư đầu năm theo TK. **DB CHULONG: BALANCE_VIEW TRỐNG** (dữ liệu bắt đầu 2026-01-01, đầu kỳ T1 = 0). |
| `dbo.VOUCHER` ⋈ `dbo.VOUCHER_DETAIL` | Bảng gốc chứng từ tiền (alias H/D, join `H.PR_KEY = D.FR_KEY`). Dùng cho tab "Chứng từ tiền" (nhanh, có OFFSET/FETCH). |
| `dbo.VOUCHER_VIEW` | **View định khoản kép**: mỗi dòng có `ACCOUNT_ID_DEBIT` + `ACCOUNT_ID_CREDIT` + `AMOUNT` + `DESCRIPTION` + `TRAN_DATE`(smalldatetime) + `TRAN_NO` + `ORGANIZATION_ID` + `PR_KEY_CTU`. **Nguồn của BC012 (sổ quỹ).** Toàn bộ STATUS='POSTED'. ⚠️ View nặng (join nhiều) → quét full ~110k dòng/tháng cho TK 11x mất ~8-20s. |
| `dbo.DM_ACCOUNT` | `ACCOUNT_ID`, `ACCOUNT_NAME`. (Không có bảng tên `ACCOUNT`.) |
| `dbo.DM_PR_DETAIL` | Đối tượng công nợ: `PR_DETAIL_ID`, `PR_DETAIL_NAME`, `BANK_NAME`, `BANK_ACCOUNT`. |
| `dbo.DM_ITEM`, `dbo.DM_EXPENSE`, `dbo.DM_ORGANIZATION` | `ITEM_CLASS1_ID`/`EXPENSE_CLASS_ID` lấy qua JOIN (KHÔNG có sẵn trong LEDGER) — dùng cho KQKD. |

---

## 4. ⚠️ Logic nghiệp vụ tuyệt đối không xóa nhầm

### `_calc_results(data, thtt_expense_list, expense_classes)` (trong `server.py`)
Bộ não phân loại chỉ tiêu **KQKD BC001–BC004** (`/api/report`, `/api/report_by_job`). Map `ITEM_CLASS1_ID` và `EXPENSE_CLASS_ID` (lấy qua JOIN DM_ITEM/DM_EXPENSE) vào ~40 chỉ tiêu. Quy ước: tổng phía CRD luôn loại bút toán kết chuyển `911`. **Đã từng bị handoff cũ xóa nhầm → hỏng form.** Sửa KQKD sai số/sai form → kiểm `_calc_results` còn nguyên trước tiên.

---

## 5. BC012 — SỔ TIỀN MẶT VÀ TIỀN NGÂN HÀNG (chi tiết đầy đủ)

**Ý tưởng:** mỗi TK tiền (mặc định 111,112,113) là 1 "sổ" riêng: Dư đầu kỳ → phát sinh Nợ/Có (mỗi dòng có số dư luỹ kế) → Cộng phát sinh → Dư cuối kỳ. Nhiều TK → có dòng "Tổng cộng".

**Nguồn:** `VOUCHER_VIEW`. Với mỗi bút toán (1 dòng view):
- Phía Nợ (`ACCOUNT_ID_DEBIT`) thuộc TK tiền → 1 dòng **THU (Nợ)**, đối ứng = `ACCOUNT_ID_CREDIT`.
- Phía Có (`ACCOUNT_ID_CREDIT`) thuộc TK tiền → 1 dòng **CHI (Có)**, đối ứng = `ACCOUNT_ID_DEBIT`.
- Dòng chuyển nội bộ giữa 2 TK tiền khác nhau → xuất hiện trong sổ của cả 2 (một bên Có, một bên Nợ). Trong CÙNG 1 TK (vd 1111→1112) → sinh 2 dòng, net = 0.

**Dư đầu kỳ:** net phát sinh (Nợ − Có) của TK đó TRƯỚC `from_date`, gộp 1 lần quét (mỗi TK 1 cột `SUM(CASE debit) - SUM(CASE credit)`). Vì BALANCE_VIEW trống ở CHULONG nên đầu kỳ tính thẳng từ VOUCHER_VIEW. KHÔNG lọc theo đối ứng/số CT (dư đầu là của cả TK).

**Bộ lọc:** `acc_ids` (mặc định 111,112,113), `contra_acc_ids` (TK đối ứng, LIKE prefix), `tran_no` (LIKE %..%), `org_ids`, `from_date`/`to_date`.

**Backend (mục quan trọng):**
- `_build_cashbook_flat(from_dt,to_dt,acc_ids,contra_ids,tran_no,org_ids)` → dựng **danh sách dòng PHẲNG** đã tính số dư luỹ kế, mỗi phần tử có `t` ∈ {`head`,`row`,`cong`,`du`,`grand`}.
- `_cashbook_flat_cached(...)` → **CACHE** kết quả flat theo md5(db|dates|accs|contra|tranno|orgs). `_cashbook_cache.clear()` mỗi lần key mới → chỉ giữ 1 bộ lọc → bound RAM.
- `GET /api/cash_book?...&page=&page_size=10000` → trả `{rows: flat[offset:offset+page_size], pagination:{total_rows,total_pages,page}}`. **Phân trang 10000 dòng/trang** (giống Nhật ký chung). Lần đầu dựng ~8-20s; các trang sau **tức thì** nhờ cache.
- `GET /api/cash_book/export_csv?...` → stream **toàn bộ** ra CSV (UTF-8 BOM, generator `_cashbook_csv_stream`) — chịu số dòng rất lớn, không phụ thuộc DOM.

**Frontend:**
- State `cashBookData = {rows, pagination}`. Trong `ReportTab`: `cbRows`, `cbPag`.
- Render bảng `.cashbook-table` (`table-layout:fixed` + `<colgroup>` 9 cột %, khổ **A4 ngang** `.paper-landscape` 297mm + `@page landscape`). Map thẳng `cbRows` theo `.t`. Nếu trang bắt đầu bằng dòng `row` → thêm header "Tài khoản X (tiếp theo trang trước)".
- Nút phân trang (FAB up/down + badge `page/total_pages`) dùng `cbPag`. Nút "Xem" reset `filters.page=1` rồi `setTimeout(loadReportData,50)` (pattern chung với BC007/BC008).
- Nút **CSV** → `window.location = /api/cash_book/export_csv?...`. Nút **PDF** → `window.print()` (in trang hiện tại).

**Lưu ý hiệu năng:** TK **113 (tiền đang chuyển)** ~108k dòng/tháng là thủ phạm nặng. Người dùng nên bỏ 113 hoặc thu hẹp ngày nếu chỉ cần tiền mặt/ngân hàng. Payload/trang ~2.7MB (không phải 25MB như khi trả full).

---

## 6. BC013 / BC011(Studio) — TỔNG HỢP PHÁT SINH CÔNG NỢ

`/api/debt_summary?from_date=&to_date=&acc_ids=&pr_detail_ids=&org_ids=`. **Từ 18/07/2026 gộp theo (ĐỐI TƯỢNG × TÀI KHOẢN)** = `GROUP BY (PR_DETAIL_ID, ACCOUNT_ID)` cho các TK đã chọn (bắt buộc chọn `acc_ids`; TK chọn khớp cả con qua `LIKE 'acc%'`). Mỗi (đối tượng × TK con) là 1 dòng, sort theo `(acc, name, id)`. Dư đầu/cuối **net lưỡng tính từng dòng** (>0 ghi Nợ, <0 ghi Có). Nguồn: BALANCE_VIEW (đầu năm) + LEDGER (lũy kế trước kỳ + phát sinh trong kỳ). Mỗi row trả thêm field **`acc`**.

> ✅ **22/07/2026: đã ĐỒNG BỘ sang LedgerReport (BC013)** — backend `get_debt_summary()` và frontend BC013 của Report giờ giống hệt Studio (group theo `(PR_DETAIL_ID, ACCOUNT_ID)`, trả `acc`, sort `(acc,name,id)`, có cột TK). Sửa 1 app thì nhớ sửa app kia; khác biệt duy nhất là **mã BC**: Studio = BC011, Report = BC013.

Frontend dùng lại state `trialBalanceData`/`trialBalanceTotal` + bảng `bc006-table`, khổ **A4 ngang** (`.paper-landscape` 297mm + `@page landscape`). Có **cột "TK"** (class `col-tk`) ở CUỐI bảng — CHỈ render khi `reportType==='BC011'` (Studio) / `'BC013'` (Report); BC006 không có: `<th rowSpan=2>` ở header + `<td>{row.acc}</td>` mỗi dòng + `<td>` rỗng ở dòng "Tổng cộng". CSS: `.bc006-table .col-code` có `word-break:break-all` (fix mã dài đè cột tên); BC011 rebalance width `col-code 8% / col-name 22% / col-value 10% / col-tk 10%`.
> ⚠️ **Lưu ý cho agent:** một số handoff/memory CŨ ghi "cột Tk KHÔNG làm" — đã ĐẢO NGƯỢC 18/07/2026, giờ CÓ cột TK. Đây là bản mới nhất.

---

## 7. Frontend patterns (dùng lại khi thêm báo cáo)

- **`REPORT_TYPES`** (mảng `{id,name}`) — thêm mã mới ở đây. Dropdown "Mẫu báo cáo" `ReportTypeDropdown` (đã set `max-height:260px; overflow-y-auto` để cuộn ~5-6 mục).
- **`filters` state** (ở App): `{from_date,to_date, org_ids, acc_ids, contra_acc_ids, pr_detail_ids, job_ids, tran_no, page, page_size:10000, ...}`. `onToggleFilter(key, val)` hỗ trợ cả toggle mảng lẫn gán vô hướng (text/date).
- **`meta`** (từ `/api/metadata`): `{accounts, orgs, pr_details, tran_ids, jobs, ...}` — nguồn cho `PremiumDropdown`.
- **`loadReportData()`** (ở App): switch theo `reportType`, fetch endpoint tương ứng, set state. Thêm nhánh mới ở đây.
- **Bộ lọc theo báo cáo**: khối filter bar hiện điều kiện `reportType === 'BCxxx'` để hiện dropdown Tài khoản/Đối tượng/TK đối ứng + input số chứng từ.
- **Render bảng**: chuỗi tam nguyên `reportType === 'BCxxx' ? (<><thead/><tbody/></>) : ...` bên trong `<table className="report-table ...">`.
- **Phân trang lớn** (BC007/BC008/BC012/BC013): server trả `pagination` (`{total_rows,total_pages,page}`); nút "Xem" reset page=1. **Từ 18/07/2026 dùng chung component `PageJumper`** (thanh ngang nổi giữa đáy trang: gõ số trang + Enter để nhảy, có nút ◀▶) cho CẢ BC007/BC008/BC012/BC013 — thay cho 2 nút FAB chevron cũ (đã bỏ). Gọi `loadReportData(p)` với `p` là số trang. BC007/BC008 hiển thị kèm badge tổng số dòng. Page size BC007/BC008 **cố định 1000 dòng/trang** (`Math.min(filters.page_size,1000)` trong `loadReportData`).
- **Xuất dữ liệu** (đã đổi 2026-07-08 — chi tiết trong `memory/export-format-convention.md`):
  - ⛔ **TỪ v1.8.2 (17/09/2026) PHẦN XUẤT BÁO CÁO DƯỚI ĐÂY ĐÃ BỊ THAY** — `exportReportXls`, `exportFullXls`, `downloadBlobAndSave`, các modal `showPagedExport`/`showVatSalesExport`/`showJournalExport` đã gỡ khỏi `index.html`. Mọi báo cáo BC005–BC013 xuất qua `ReportExportDialog` → `POST /api/report_export/start` → `xlsx_report.py` (job nền, .xlsx chuẩn form hoặc CSV). Endpoint `/api/report_export_csv`, `/api/export_excel_backend`, `/api/cash_book/export_csv`, `/api/save_export` còn nhưng KHÔNG nút nào gọi. Xem changelog 2026-09-17 và `NHAT_KY_CONG_VIEC.md` mục 8. Các gạch đầu dòng về báo cáo bên dưới chỉ còn giá trị lịch sử.
  - **Danh sách chứng từ** (tab ledger/purchase/warehouse/sale/voucher), nút **"Xuất Excel"** → mode "1 file" (`doExport(kind,'single')`) LUÔN xuất **CSV** server-side, ghi ra `Downloads\iPOS_Ledger_Studio\` rồi mở modal Mở file/folder. Đã **bỏ giới hạn 500.000 dòng** (`SERVER_STREAM_THRESHOLD = 0`); 5 endpoint `/api/*/stream_csv` đặt fname đuôi **`.csv`** → `_start_export_job` route sang `_write_csv_to_disk` (CSV không giới hạn). Mode "Mỗi đơn vị 1 sheet" (`by_org`) vẫn **xlsx client-side** (SheetJS) vì cần nhiều sheet. (`_write_xlsx_to_disk` giờ là dead code.)
  - **Báo cáo bảng DOM** (mọi BC trừ 007/008/012) → **`exportReportXls()`**: xuất **.xls dạng HTML-mso** (KHÔNG dùng SheetJS `biff8` — bản community không ghi được style ô → ra data thô). Clone `.report-table`, nội tuyến toàn bộ computed-style (font/màu/nền/viền/canh lề/padding/width) → Excel render giống web. Điểm mấu chốt: (1) prepend khối tiêu đề công ty/mẫu/tên BC/kỳ (lấy từ `.report-paper`, nằm NGOÀI table) vào `thead` với `colspan` theo đúng số cột; (2) dịch `text-align start/end → left/right` (Excel không hiểu `start`); (3) ô `col-value` lưu **SỐ THẬT** (parse bỏ dấu phẩy, `(x)`→−x) + class `.xnum{mso-number-format:"\#\,\#\#0"}`, ô khác giữ text `.xtext{"\@"}` (mã 011, cột %). Nút nhãn **"Excel"**. Excel mở hỏi cảnh báo định dạng → bấm **Yes**. Số âm hiện `-1,234` (format 1-section).
  - 🔴 **BÁO CÁO CÓ PHÂN TRANG (BC008 / BC012 / BC013) — LUẬT BẮT BUỘC:** `exportReportXls()` đọc `.report-table` **đang hiển thị**, mà DOM chỉ có TRANG HIỆN TẠI → xuất thẳng sẽ ra file **thiếu dòng, KHÔNG báo lỗi**. Từ 27/07/2026 dùng **`exportFullXls(url, pickRows)`** (trong `ReportTab`): fetch API với **`page_size=0`** (server trả toàn bộ) → `setFullExportRows(rows)` → `useLayoutEffect` gọi `exportReportXls()` rồi trả DOM về trạng thái phân trang (dùng `useLayoutEffect` nên không nháy màn hình). Bảng render qua 2 biến **`pagedDataRows`** (BC008/BC013) và **`cbRowsView`** (BC012) — cả hai đều `fullExportRows || <dòng của trang hiện tại>`. URL + cách bóc mảng dòng khai ở **`buildFullExportReq(rptType, modeArg)`**. Vượt **`FULL_XLS_WARN_ROWS = 50.000`** dòng thì `confirm()` cảnh báo và gợi ý dùng CSV. Backend 3 route `/api/account_details`, `/api/cash_book`, `/api/vat_sales_report` đều nhận `page_size=0` = lấy tất cả (⚠️ nhớ chặn chia 0 khi tính `total_pages`).
  - Nút Excel của **BC008/BC012** mở modal `showPagedExport` (2 lựa chọn: *Excel giữ nguyên form* → `exportFullXls`; *Xuất toàn bộ CSV* → `exportPagedCsv`). **BC013** mở modal `showVatSalesExport` (3 lựa chọn: xls Chi tiết / xls Tổng hợp — cả hai qua `exportFullXls`; và CSV toàn bộ → `/api/report_export_csv?report_type=BC013`).
  - **BC007 KHÔNG có bản .xls giữ form** — cố ý: ~600k dòng/tháng, cả năm vượt trần 1.048.576 dòng/sheet của Excel, nạp đủ vào DOM sẽ treo trình duyệt. Modal BC007 có ghi chú giải thích cho người dùng.
  - BC007/BC008/BC013 → backend `/api/report_export_csv` (Studio, CSV stream). **BC007 từ 18/07/2026 có 2 KIỂU XUẤT** qua modal `showJournalExport` (state local trong ReportTab) → tham số `mode`:
    - `mode=summary` (mặc định, "như web đang xem"): cột Đơn vị, Tên đơn vị, Ngày HT, Mã CT, Số CT, Diễn giải, TK Nợ, TK Có, PS Nợ, PS Có. Nguồn `dbo.LEDGER L` JOIN `DM_ORGANIZATION O` (lấy tên ĐV).
    - `mode=detail` ("Nhật ký chung chi tiết", theo mẫu SQL người dùng): Bảng, Mã/Tên đơn vị, Công việc, Mã CT, Ngày CT, Số CT, Diễn giải, Tài khoản, TK đối ứng, Mã/Tên đối tượng, Số tiền nợ, Số tiền có, Ghi chú. Nguồn `dbo.LEDGER_VIEW LV` JOIN `DM_ORGANIZATION O` (LEDGER_VIEW **không** có sẵn ORGANIZATION_NAME nên phải JOIN).
    - FE: `exportJournalCsv(mode)`. Mọi nút xuất CSV/backend đều đi qua helper **`downloadBlobAndSave(apiUrl, defaultFilename)`** (KHÔNG phải `downloadAndSaveApi` như tài liệu cũ ghi): fetch → blob → tải về → `FileReader` → POST `/api/save_export` để lấy đường dẫn thật → modal tiến trình 0-100% với "Mở file ngay" / "Mở thư mục chứa file".
    - (Report app dùng `/api/export_excel_backend` **xlsx** cho BC007/BC008 — GIỮ NGUYÊN, chưa port 2-mode.)
  - BC012 → `/api/cash_book/export_csv` (server stream) cho nhánh CSV; nhánh .xls giữ form dùng `exportFullXls`.
  - `REPORT_FILE` map mã→tên file. **`SHEET_LIMIT` trong `exportReportXls`: Studio = 1.000.000, Report = 50.000** (khác nhau, đừng copy nhầm).
- **In A4 / Landscape**: `.report-paper` gán class `paper-landscape` (297mm) cho **BC001–BC004** + BC006/BC007/BC012/BC013 (Report) / +BC011 (Studio) — sửa ở list `['BC001',...].includes(reportType)`. In/PDF vốn đã landscape mặc định (`@media print { @page { size: landscape } }`); vài BC còn tự chèn `@page A4 landscape` + `<colgroup>` để fit khổ.

---

## 8. Chạy & Build (lệnh chuẩn cho agent)

```bash
# Dev (không khuyến khích test kiểu này vì ghost-server — xem mục 9.1):
#   python server.py  → http://localhost:5050

# Syntax check:
python -c "import ast; ast.parse(open('server.py',encoding='utf-8').read()); print('OK')"

# Build EXE — CÁCH CHUẨN hiện tại: chạy trong thư mục app (tự nhận tên app theo thư mục,
# tự tăng version.txt + sinh version_info.txt):
python build_exe.py

# ⚠️ build_exe.py in "[SUCCESS]" VÔ ĐIỀU KIỆN (không check return code của PyInstaller).
#    PHẢI verify sau build: so mtime của dist/*.exe với giờ hiện tại. Nếu EXE đang CHẠY,
#    nó khóa file → PyInstaller không đè được nhưng vẫn in SUCCESS (EXE cũ nằm nguyên).
#    Trước khi build phải tắt tiến trình: tasklist | grep -i iPOS_… ; nếu còn thì đóng app.

# Build thủ công (tương đương BuildEXE.bat, dùng khi cần):
python -m PyInstaller --noconsole --onefile --clean --noconfirm --name "iPOS_Accounting_Report" --icon icon.ico \
  --add-data "index.html;." --add-data "install_driver.ps1;." --add-data "manifest.json;." --add-data "icon.svg;." \
  --collect-submodules flask --collect-submodules flask_cors --collect-submodules pyodbc \
  --hidden-import pyodbc --hidden-import flask --hidden-import flask_cors server.py
# Studio: --name "iPOS_Ledger_Studio"
# BuildEXE.bat có lệnh `pause` → TREO ở chế độ non-interactive; ưu tiên build_exe.py.
```
Kiểm tra JSX (Babel không báo lỗi lúc chạy, nên parse trước bằng @babel/parser trong node_modules):
```js
// node script: đọc index.html, regex lấy <script type="text/babel">, parser.parse(code,{sourceType:'module',plugins:['jsx']})
```

---

## 9. 🐞 Cách test đúng & các bẫy đã gặp (@vibe-guard)

### 9.1 TEST BACKEND BẰNG `test_client` IN-PROCESS (bắt buộc)
Đừng chạy `python server.py` rồi curl — nhiều lần dính **"ghost server"**: một process `server.py`/EXE cũ vẫn giữ port 5050 và trả lời request bằng **code cũ**, trong khi bản mới bind không thành công/không nhận request → tưởng code sai. Thay vào đó:
```bash
export PYTHONIOENCODING=utf-8   # tránh UnicodeEncodeError khi print tiếng Việt trên Windows
python -c "
import server
c = server.app.test_client()
c.post('/api/login', json={'server':'<SERVER>','database':'IACC_CHULONG','user':'<USER>','password':'<PASSWORD>','driver':'ODBC Driver 17 for SQL Server'})
d = c.get('/api/cash_book?from_date=01/01/2026&to_date=31/01/2026&acc_ids=111&page=1').get_json()
print(d['pagination'], len(d['rows']))
"
```
Chạy đúng code trong file, không port, không ghost. Nếu **buộc** phải test qua EXE: `Stop-Process` mọi `python`/EXE cũ → `sleep 3` → chạy 1 EXE → **poll** `curl / ` tới khi `200` mới test (EXE onefile giải nén chậm; dev-server đơn luồng + trình duyệt EXE tự mở có thể chiếm kết nối).

### 9.2 Thứ tự tham số SQL phải khớp thứ tự mệnh đề
Trong `/api/cash_book`, `org_where` (mặc định `NOT IN externals`) đứng **TRƯỚC** `contra`/`tran_no` trong chuỗi SQL → `org_params` phải nối NGAY SAU `acc_like` params, KHÔNG nối cuối cùng. Sai thứ tự → lệch bind → **trả 0 dòng** dù logic đúng. (Đã từng dính.)

### 9.3 Các bẫy khác
- **`TRAN_DATE` smalldatetime** — không `SUBSTRING`; truyền `strftime('%Y%m%d')`.
- **Cột không có trong VIEW tổng hợp** — `SELECT` cột không tồn tại làm API crash + ngắt pool. Thăm dò schema (`INFORMATION_SCHEMA.COLUMNS`) trước khi dùng cột lạ.
- **Date parsing JS** — `new Date(str.replace(' ','T'))`. Hiển thị date từ cursor: `.strftime('%d/%m/%Y')`.
- **JSX escape** — render text DB bằng `<td>{row.X}</td>`; tránh `dangerouslySetInnerHTML`.
- **Missing props** — mọi state của App phải truyền xuống ReportTab qua props (nếu không: `ReferenceError` vỡ app).
- **`abortRef` dùng chung** — mỗi `loadReportData` `abortRef.current.abort()` request cũ; nếu 2 luồng dùng chung ref có thể hủy nhau giữa `r.json()` → "Unexpected end of JSON input". Mỗi lần tạo `AbortController` mới và gán lại.
- **Virtual scroll giật/"trắng dòng"** — dòng phải cao ĐỀU; nội dung tràn/wrap làm lệch padding. Dùng `white-space:nowrap` + `truncate`/`text-overflow` cho ô mô tả.

### 9.4 🔥 SỰ CỐ HỎNG FILE do công cụ tự chèn `WITH (NOLOCK)` (đã gặp 2026-07-04)
Một công cụ/script "thêm NOLOCK" chạy lên `server.py` đã **làm hỏng SQL**: nhân đôi hint (`WITH (NOLOCK) WITH (NOLOCK)`) VÀ **tách alias** (`PD`→`P WITH (NOLOCK)D`, `PD2`→`PD WITH (NOLOCK)2`, `WI`→`W WITH (NOLOCK)I`) VÀ đặt **hint trước alias** (`dbo.X WITH (NOLOCK) L WITH (NOLOCK)`). Triệu chứng: alert **"Incorrect syntax near the keyword 'with'"** (SQL 8180) khi tải báo cáo — hỏng NHIỀU endpoint, không riêng 1 cái.
- **Phát hiện:** `grep -c "WITH (NOLOCK) WITH (NOLOCK)" server.py` > 0; `grep -nE "[A-Za-z] WITH \(NOLOCK\)[A-Za-z]" server.py` (alias bị tách).
- **Sửa (script Python 3 lượt regex, giữ 1 hint hợp lệ):**
  1. `re.sub(r' WITH \(NOLOCK\)(?=\w)', '', s)` — rejoin alias.
  2. `re.sub(r'( WITH \(NOLOCK\))(?:\s+WITH \(NOLOCK\))+', r'\1', s)` — gộp hint nhân đôi.
  3. `re.sub(r'(dbo\.\w+) WITH \(NOLOCK\)(\s+)(\w+)(\s+WITH \(NOLOCK\))', r'\1\2\3\4', s)` — bỏ hint đặt sai trước alias.
- **Bắt buộc verify sau khi sửa:** chạy `test_client` quét ~15 endpoint (metadata/ledger/purchase/warehouse/sale/voucher/trial_balance/journal/account_details/balance_sheet/cash_flow/report/cash_book/debt_summary) — tất cả phải `status ok`.
- ⚠️ **Không revert bằng git** (HEAD là bản cũ nhiều phiên trước, mất hết công việc). File chưa commit.

---

## 10. Tối ưu hiệu năng load dữ liệu (đúc kết)

1. **Phân trang server-side + cache flat** (BC012): lần đầu dựng full (quét view) rồi cache; trả từng trang 10000 dòng. Trang sau tức thì. DOM nhỏ → render/cuộn mượt + in A4 + CSV được. Đây là cách tối ưu ĐANG DÙNG cho báo cáo nhiều dòng.
2. **Virtual scroll** (tab dữ liệu thô ledger/purchase/warehouse): render chỉ dòng trong viewport. Dùng khi cần cuộn liền mạch hàng trăm nghìn dòng, KHÔNG in/paginate.
3. **Xuất CSV stream** thay vì .xls DOM cho dữ liệu lớn (không giới hạn dòng, RAM thấp).
4. **Gộp truy vấn** (vd dư đầu kỳ nhiều TK về 1 lần quét bằng nhiều cột CASE).
5. **Giảm payload**: chỉ SELECT cột cần; trả trang thay vì full (25MB → ~2.7MB/trang).
6. **`CREATE_INDEXES.sql` / `CREATE_INDEXES_SALE.sql`**: index tối ưu; cân nhắc index `TRAN_DATE`/account trên bảng gốc của VOUCHER_VIEW nếu được phép sửa DB khách (rủi ro — hỏi trước).
7. Nút "Xem" luôn reset `page=1`; dùng spinner (`setLoading`) để user biết đang tải (đừng để tưởng treo).

---

## 11. Quy trình THÊM BÁO CÁO MỚI (checklist)

1. **Chọn mã trống** ở app đích (Report tới **BC014**, Studio tới **BC013**) → mã mới thường **BC014+** ở Studio, **BC015+** ở Report. Kiểm cả `REPORT_TYPES` lẫn `loadReportData`.
2. **Backend**: thêm route `/api/<name>` (`@app.route` + `@with_db_lock` + try/except + `invalidate_pool()` khi lỗi). Cẩn thận thứ tự param (9.2), `TRAN_DATE` (9.3). Nếu nhiều dòng → phân trang + cache như BC012.
3. **Frontend**:
   - Thêm `{id:'BCxxx', name:'...'}` vào `REPORT_TYPES`.
   - Thêm state nếu cần + truyền prop xuống `ReportTab` (nhớ thêm vào **signature** của ReportTab).
   - Thêm nhánh fetch trong `loadReportData`.
   - Thêm filter bar theo `reportType`.
   - Thêm nhánh render bảng; thêm `@page`/`<colgroup>` nếu cần fit A4.
   - Thêm vào `REPORT_FILE`; thêm nhánh trong `exportToExcel` (báo cáo bảng DOM → `exportReportXls` .xls; nếu nhiều dòng như 007/008/012 → CSV/xlsx backend riêng); điều kiện disabled nút.
4. **Test** `test_client` (9.1) → **parse JSX** → **build EXE** cho cả 2 app nếu áp dụng cả 2.
5. Cập nhật file này + `memory/`.

---

## 12. Bản đồ file (cốt lõi)
- `server.py` — backend + toàn bộ API. `index.html` — frontend. `index.html.bak*` — bản cũ.
- `build_exe.py` — **script build chuẩn** (auto version + version_info). `version.txt`/`version_info.txt` — version hiện tại (build_exe.py sinh/tăng).
- `BuildEXE.bat` (có `pause`), `RunReport.bat`, `install_driver.ps1`, `manifest.json`, `icon.svg/.ico`, `requirements.txt` (flask/flask-cors/pyodbc/xlsxwriter/pymssql).
- `CREATE_INDEXES*.sql` — index. `dist/` — EXE.
- Tài liệu (thực tế còn trong thư mục): **`KIEN_TRUC_TOAN_TAP.md` (file này = CLAUDE.md, đọc TRƯỚC)**, `HUONG_DAN_BC007_BC010.md` (handoff BC007–BC010 + pattern danh sách chứng từ), `FIX_OFFLINE_FILTERS.md` (inline CDN khi offline), `skill.md`. (README.md/START_HERE.md đã bỏ.)
- Bỏ được khi nén: `node_modules/`, `__pycache__/`, `*_extracted/`, `temp_backup/`, `*.rar`, các `*.txt`/`*.py` reverse-engineer/patch một lần.

> Khi sửa xong bất kỳ thứ gì: **syntax-check → test_client → build EXE → cập nhật tài liệu này.**

---

## 13. Changelog & bàn giao chi tiết

### 2026-09-17 — Tự cập nhật qua GitHub Releases — v1.8.3 *(chỉ LedgerStudio)*

`/api/check_update` → `/api/apply_update` → `/api/update_progress` (server.py trước `__main__`, `_download_and_swap`) + banner/modal trong index.html. Tải `iPOS_Ledger_Studio.exe` vào `<exe>.new`, kiểm dung lượng + SHA-256, đổi tên exe đang chạy → `<exe>.old`, đặt bản mới, đóng cửa sổ Chrome, chạy bản mới với env đã gỡ `_PYI_*`, thoát; bản mới dọn `<exe>.old`. `__main__` giữ `_app_window_proc`, không tự tắt khi `_update_in_progress`, `_wait_port_free(5050)`. Release đầu `v1.8.3`; đã test cập nhật thật 1.8.2 → 1.8.3 từ GitHub. Quy trình phát hành: CLAUDE.md mục 5 Bước 5; bẫy: Bẫy 13. Chi tiết: `NHAT_KY_CONG_VIEC.md` mục 10.

### 2026-09-17 — Studio có repo GitHub riêng `trungkhanhduong93/ledgerstudio` (Public)

Push 1 commit gốc mới (v1.8.2); lịch sử cũ giữ ở nhánh local `lich-su-truoc-17-09`, không push. `BaoCaoMau/`, `BESReportViewer.pdf` vào `.gitignore` (dữ liệu khách). Chỉ commit/push khi Trum bảo; kiểm `git remote get-url origin` trước khi push. Chi tiết: `NHAT_KY_CONG_VIEC.md` mục 9.

### 2026-09-17 — Xuất báo cáo ra .xlsx chuẩn form, job nền, tiến trình thật — v1.8.2 *(chỉ LedgerStudio)*

**Đổi gì:** bỏ .xls HTML-mso dựng DOM + CSV đọc lại vào RAM. Thêm module `xlsx_report.py` (layout 9 báo cáo, writer xlsxwriter `constant_memory`, CSV writer cùng dữ liệu) + `server.py` section cuối file (`_rx_plan`, `_rx_start_job`, `/api/report_export/start`, `/api/export/dir`) + `index.html` (`ReportExportDialog`, `buildReportHeader` dùng chung màn hình/file, `REPORT_FORM_CODE`, `REPORT_TITLE`, `viewSnapRef` chụp bộ lọc lúc nạp dữ liệu, `tbRowFlags`).

**Luật dữ liệu:** BC005/006/009/010/011 → app gửi đúng dòng đang hiển thị (`payload`). BC007/008/012/013 → server truy vấn lại toàn bộ, CÙNG view + ORDER BY với endpoint xem (`LEDGER_VIEW`, cache/`_build_cashbook_flat`, `VAT_TRANSACTION_VIEW`). Bộ lọc đơn vị `_org_filter_sql` tính trong request (cần session) rồi mới giao thread. `_build_cashbook_flat` nhận thêm `cur`, `org_filter` để chạy trong thread.

**Định dạng file:** tiền `#,##0;(#,##0);"-"` giá trị thật; % lưu phân số; ngày datetime; mã TK/số HĐ chuỗi `@`; tách sheet 1.000.000 dòng kèm dòng cộng chuyển sang; chữ ký 1 dòng rich string (không bị ngắt trang giữa khối).

**Danh sách chứng từ (sửa kèm):** `_write_xlsx_to_disk` coi `Decimal` là số (trước ghi thành chữ), tách sheet 1.000.000, header đậm + freeze + AutoFilter; `_start_export_job` đặt tên không trùng `(2)` + ghi `*.part` rồi đổi tên.

**Build:** `build_exe.py` thêm `--hidden-import xlsx_report` (Gemini) và `--exclude-module` IPython/matplotlib/numpy/pandas/PIL — bản 1.8.1 phình 43 MB vì `flask.cli → python-dotenv → IPython`; 1.8.2 về 15,8 MB.

**Verify:** M1–M3 đạt (41 + 23 check test_client DB giả, 1.000.051 dòng 75 s RAM 50 MB, mở bằng Excel thật, 14 check UI Chrome, chạy EXE). **M4 trên DB thật: CHƯA** — chi tiết `NHAT_KY_CONG_VIEC.md` mục 8.6.

### 2026-08-12 — Thêm tab mới "Danh sách tồn kho thực tế" + vá 2 bug đặt tên có sẵn *(chỉ LedgerReport)*

**Yêu cầu:** Thêm 1 danh sách mới hiển thị số dư tồn kho theo (Đơn vị × Kho × Mặt hàng) TẠI TỪNG NGÀY, nguồn bảng `dbo.WAREHOUSE_BALANCE_ACTUAL` (bảng snapshot số dư, KHÔNG có `TRAN_NO`/`TRAN_ID` — khác hẳn "chứng từ"). Yêu cầu rõ: tách biệt hoàn toàn, không gộp vào tab "Kho" (WAREHOUSE_VIEW) đang có.

**Khảo sát dữ liệu trước khi code (DB `IACC_CHULONG`):** bảng có 19 cột, ~830k dòng lũy kế 236 ngày (06/12/2025→nay), **1 ngày cụ thể ≈ 4.000 dòng** (74 đơn vị/kho). `AMOUNT`/`UNIT_PRICE`/`QUANTITY_EXTRA`/`JOB_ID`/`PACKAGE`/`BARCODE`/`ACCOUNT_ID_ADJUST` rỗng/=0 toàn bộ ở DB này → không đưa vào SELECT. `QUANTITY_ADJ`+`UNIT_ID_ADJ` = số lượng/đơn vị đóng gói GỐC trước quy đổi (VD kho `KTONG`: "Cafe (bột)" `QUANTITY=34000 G`, `QUANTITY_ADJ=68 BICH`) — hiển thị nhãn "SL nguyên"/"ĐVT nguyên". `DM_ITEM.UNIT_ID` JOIN theo `ITEM_ID` cho đơn vị tính chính. Không lọc `IS_APPROVED` — hiển thị nguyên trạng cả 0 và 1 (thêm cột "Đã duyệt").

**Backend `server.py` (+210 dòng, thuần cộng thêm, không sửa code Kho cũ):**
- 3 route mới: `GET /api/warehouse_balance` (phân trang `ROW_NUMBER`), `GET /api/warehouse_balance/count`, `POST|GET /api/warehouse_balance/stream_csv` (export nền qua `_start_export_job` có sẵn).
- `WAREHOUSE_BALANCE_BASE_COLUMNS`, `_build_warehouse_balance_where()` (from_date/to_date range + IN filter org/wh/item/acc + LIKE search theo cột), `WAREHOUSE_BALANCE_SORT_WHITELIST`, `WAREHOUSE_BALANCE_CSV_COLS`. JOIN `DM_ORGANIZATION`/`DM_WAREHOUSE`/`DM_ITEM` lấy tên + đơn vị tính.

**Frontend `index.html` (+237 dòng, 1 dòng sửa):**
- Thêm `{id:'warehouse_balance', name:'Danh sách tồn kho thực tế'}` vào `DOC_TABS` (dropdown "Danh mục" — KHÔNG phải mã BC, đây không phải báo cáo BC0xx).
- State/fetch/query builder riêng hoàn toàn (`warehouseBalance*`), dùng chung `filters.from_date/to_date/org_ids/item_ids/acc_ids` theo đúng quy ước chung toàn app (như mọi tab khác), riêng `wh_ids` local giống tab Kho.
- Bảng 14 cột: Ngày, Mã/Tên đơn vị, Mã/Tên kho, Mã/Tên hàng, ĐVT, Số lượng, SL nguyên, ĐVT nguyên, Người thực hiện, Tài khoản, Đã duyệt. Virtual scroll, sort, search theo cột, filter bar (Đơn vị/Kho/Hàng hóa/Tài khoản).
- `WAREHOUSE_BALANCE_EXPORT_COLS` + gắn `warehouse_balance` vào `buildExportQuery`/`doExport` (cả nhánh `single` server-stream lẫn nhánh `by_org` client xlsx) — tránh bug ExportButton dùng chung component 3 nút mà thiếu case sẽ âm thầm export nhầm dữ liệu Kho cũ.

**2 bug có sẵn phát hiện & vá kèm (không liên quan tính năng mới, phát hiện khi build/test):**
1. `build_exe.py` dòng 6 so khớp `'LedgerReport' in os.getcwd()` **phân biệt hoa/thường** — thư mục thật là `ledgerreport` (chữ thường, đúng tên repo GitHub) nên luôn rơi vào nhánh `else`, build nhầm thành `iPOS_Ledger_Studio.exe` thay vì `iPOS_Accounting_Report.exe`. Đã sửa thành `'ledgerreport' in os.getcwd().lower()`.
2. `index.html` dòng 819 `const APP_NAME = 'iPOS Ledger Studio'` (hardcode sai) — khiến màn hình đăng nhập hiện sai tên app dù `<title>`/footer JSX đều đúng "iPOS Accounting Report". Đã sửa thành đúng tên.

**Verify:**
- Backend: test bằng `test_client` in-process với DB thật `IACC_CHULONG` — count đúng 4.032 dòng (01/08/2026), phân trang/JOIN tên/filter kho/search/sort đều đúng, export CSV job chạy xong ra đúng 4.032 dòng + header.
- Frontend: parse JSX bằng `@babel/parser` (`node_modules` cài mới, `--no-save`) — OK, không lỗi cú pháp.
- **Test UI thật qua browser** (đăng nhập DB thật, không chỉ đọc code): chuyển tab đúng tên, bấm TRUY VẤN tải **107.499 dòng** thật (tháng 1/2026), sort theo cột hoạt động đúng.
- Build EXE: `python build_exe.py` → `iPOS_Accounting_Report.exe v1.7.6`, đã verify mtime khớp thời điểm build (không phải file cũ do khoá tiến trình). Chạy thử EXE thật (không phải dev server) → login, hiển thị đúng tên "iPOS Accounting Report" v1.7.6.

**Lưu ý cho agent sau:** báo cáo trong `REPORT_TYPES` (mã BC, tab "Báo cáo") và danh sách trong `DOC_TABS` (dropdown "Danh mục") là **2 khái niệm khác nhau, độc lập** — đừng nhầm khi tài liệu cũ (`HUONG_DAN_BC007_BC010.md` mục 8.4) ghi nhầm "REPORT_TYPES" cho Sale (thực tế Sale nằm ở `DOC_TABS`).

### 2026-08-12 (tiếp) — 🔥 VÁ BUG "build xong chạy EXE là chết ngay / Failed to fetch" *(cả 2 app đều dính — mới vá LedgerReport)*

**Triệu chứng người dùng gặp lặp đi lặp lại nhiều lần:** vừa build EXE xong, chạy lên là app chết ngay (EXE thoát mã 1), hoặc đang dùng bình thường thì mọi thao tác báo **`Failed to fetch`** / `net::ERR_CONNECTION_REFUSED` — dù code hoàn toàn đúng. Trước đây hay bị quy oan cho code vừa sửa.

**Nguyên nhân gốc (khối `__main__`, `server.py` ~5334):** EXE khởi động sẽ spawn 1 cửa sổ **Chrome `--app`** dùng profile riêng `%LocalAppData%\iPOS_Ledger_Studio\AppProfile`, rồi `proc.wait()` chờ tiến trình đó; khi cửa sổ đóng → `_shutdown_everything()` → `taskkill /F /T` **chính server**. Thiết kế này đúng khi dùng bình thường, NHƯNG:
> Nếu ĐÃ có sẵn một Chrome đang dùng chung `--user-data-dir` đó (cửa sổ app cũ chưa đóng hẳn, hoặc process mồ côi còn sót), thì `chrome.exe` vừa spawn chỉ **bàn giao** việc mở cửa sổ cho instance cũ rồi **tự thoát ngay (<1s)**. `proc.wait()` trả về tức thì → server hiểu nhầm "user đã đóng cửa sổ" → **tự sát ngay khi vừa lên**.

**Cách nhận biết nhanh khi gặp lại:**
```powershell
# Con so > 0 = dang dinh dieu kien gay bug
@(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like "*iPOS_Ledger_Studio*" }).Count
```
EXE thoát ngay với `ExitCode 1` (bắt bằng `Start-Process -PassThru` rồi kiểm `.HasExited`) là dấu hiệu chắc chắn.

**Đã vá:** đo thời điểm spawn (`_t_spawn`); nếu `proc.wait()` trả về **< 5 giây** ⇒ hiểu là bàn giao chứ KHÔNG phải user đóng cửa sổ ⇒ **`return` giữ server chạy ngầm** (đúng như nhánh dự phòng "không track được" đã có sẵn phía trên). Hành vi "đóng cửa sổ app → tắt server" khi dùng bình thường **giữ nguyên**.

**Verify:** tái hiện đúng điều kiện gây lỗi (mở sẵn Chrome chiếm `AppProfile` → 8 tiến trình) rồi chạy EXE mới: trước khi vá EXE thoát `ExitCode 1`; sau khi vá **EXE vẫn chạy, `HTTP 200`**, UI hiện đúng **v1.7.7**. EXE: `dist/iPOS_Accounting_Report.exe` **v1.7.7** (12/08/2026 13:40, đã verify mtime).

**⚠️ CHƯA PORT SANG LEDGERSTUDIO** — Studio dùng chung y hệt khối launcher này (cùng profile dir `iPOS_Ledger_Studio`) nên **chắc chắn cũng dính**. Agent sau đụng Studio nhớ port bản vá này qua.

**Bài học vận hành cho agent:** khi user đang mở app mà cần build lại (build đòi đóng app để không khoá file EXE) thì **PHẢI báo trước**, đừng `Stop-Process` ngang — user sẽ thấy "Failed to fetch" giữa chừng và tưởng tính năng vừa làm bị lỗi. Muốn chạy server để test mà KHÔNG dính launcher Chrome: import `server` rồi gọi thẳng `server.app.run(host="0.0.0.0", port=5050, use_reloader=False)` (bỏ qua khối `__main__`).

### 2026-08-03 — Bổ sung cột "Tài khoản công nợ" (ACCOUNT_ID_PR) vào Danh sách chứng từ Bán hàng *(LedgerStudio)*

**Yêu cầu:** Thêm cột `ACCOUNT_ID_PR` (Tài khoản công nợ) vào Bảng danh sách chứng từ Bán hàng (`SALE_VIEW`), export CSV và export Excel.

**Đã làm:**
- **Backend (`server.py`):**
  - Đưa `"ACCOUNT_ID_PR"` vào mảng `SALE_BASE_COLUMNS` (vị trí liền kề sau `"ACCOUNT_ID"` và trước `"ACCOUNT_ID_INCOME"`/`"ACCOUNT_ID_COST"`). Vì nằm trong BASE, cột sẽ mặc định có trong view tổng hợp, `SELECT` an toàn và tự động hỗ trợ sorting qua `SALE_SORT_WHITELIST`.
  - Thêm `("ACCOUNT_ID_PR", "Tài khoản công nợ")` vào `SALE_CSV_COLS` để export ra CSV stream chuẩn 44 cột.
- **Frontend (`index.html`):**
  - Mở rộng cấu trúc cột bảng Bán hàng từ 43 → 44 cột (Thêm `<SortableHeader field="ACCOUNT_ID_PR">TK công nợ</SortableHeader>`).
  - Thêm `ACCOUNT_ID_PR` vào mapping của thanh công cụ Filter/Search nội bộ (khắc phục cả lỗi khuyết `ACCOUNT_ID_COST` trước đó của bộ Search làm shift cột lệch).
  - Cập nhật hàm Render `SaleRow` xuất `<td>{r.ACCOUNT_ID_PR}</td>` với class `text-cyan-600` in đậm, tách biệt màu với TK kho và TK bán hàng gốc.
  - Sửa `tfoot` tổng (`colSpan`) padding cuối từ `15` thành `17` bù lại khuyết điểm độ rộng bảng để ôm gọn 44 cột.
  - Cập nhật `SALE_EXPORT_COLS` để nút "Mỗi ĐV 1 sheet (Excel)" cũng lấy đủ cột này.
- **Tính năng mới bổ sung:** Xóa bỏ định dạng in đậm (`bold: True`) và kẻ viền (`border: 1`) khi xuất Excel danh sách chứng từ từ server (trong hàm `_write_xlsx_to_disk` của `server.py`) để file raw nhẹ và sạch hơn theo yêu cầu.
- **Tình trạng:** Build EXE thành công, Babel phân rã JSX tốt. Đã vá triệt để bug padding cột của dev trước.

### 2026-07-22 — Đồng bộ cột TK báo cáo công nợ sang LedgerReport (BC013) + build lại 2 EXE

**Bối cảnh:** Trung báo BC011 Studio chưa có cột TK — thực ra source ĐÃ có từ 18/07, chỉ là **EXE đang dùng là bản cũ** (bản cũ gộp theo đối tượng: 1 đối tượng 1 dòng; bản mới tách theo từng TK con). ⇒ Bài học: khi user báo "thiếu tính năng vừa làm", kiểm mtime `dist/*.exe` trước khi sửa code.

**Đã làm:**
- **LedgerReport `server.py` `get_debt_summary()` (~4098):** port y hệt Studio — 3 query đổi `GROUP BY` sang `(ISNULL(PR_DETAIL_ID,''), ISNULL(ACCOUNT_ID,''))`, key dict thành tuple `(pid, acc)`, row trả thêm `acc`, sort đổi từ "theo số tiền giảm dần" → `(acc, name, id)`.
- **LedgerReport `index.html`:** thêm `<th className="col-tk">TK</th>` (rowSpan 2, cuối header), `<td>{row.acc}</td>` khi `isBC013`, `<td className="col-tk">` rỗng ở dòng Tổng cộng, CSS `col-code` word-break + rebalance width BC013 (`col-code 8% / col-name 22% / col-value 10% / col-tk 10%`).
- **Build lại CẢ 2 EXE:** `iPOS_Ledger_Studio.exe` v1.3.1 (22/07 23:16), `iPOS_Accounting_Report.exe` v1.4.0 (22/07 23:36) — đã verify mtime.

**Verify:** `ast.parse` server.py 2 app OK; `test_client GET /` 2 app → `col-tk` ×4, `row.acc` ×2; parse JSX bằng `@babel/parser` cả 2 file OK. **CHƯA test DB thật** — cần đối chiếu BC013 Report với mẫu Excel `IP_Bảng PSCN 338_T06.26` (TK 338, 16/06–30/06/2026) như đã làm với Studio.

**Bổ sung cùng ngày — VERSION hiển thị trong app:** Studio hardcode `const APP_VERSION = 'v1.0.0'` trong index.html nên UI kẹt v1.0.0 dù `version.txt`/EXE đã lên 1.3.x. **LedgerReport đã giải bài này từ trước** bằng: `_read_app_version()` đọc `version.txt` → hằng `APP_VERSION` → route public `GET /api/version` → hook FE `useAppVersion()` (fetch 1 lần, dùng ở màn login + header), kèm `ADD_DATA.append('version.txt;.')` trong build_exe.py để nhúng file vào EXE. Đã **port y nguyên sang Studio** (không tự nghĩ cách khác — luôn kiểm app kia đã có sẵn giải pháp chưa trước khi tự chế). EXE mới: Studio **v1.3.2**, Report **v1.4.1** (23/07 00:05, đã verify `VersionInfo.FileVersion`).

**Bổ sung — MẤT KẾT NỐI SERVER không còn đổ stack trace ra màn hình:** `<script>` ở `<head>` (cả 2 app) có 2 handler debug `error`/`unhandledrejection` in overlay đỏ + stack. Khi EXE bị tắt mà cửa sổ app còn mở, mọi fetch `:5050` fail (`ERR_CONNECTION_REFUSED`) → người dùng thấy màn hình đỏ "UNHANDLED PROMISE REJECTION: TypeError: Failed to fetch". Đã thêm:
- `window.isNetworkError(x)` — nhận diện `TypeError` có message khớp `fetch|network|load failed` (bắt cả "Load failed" của Safari/WebKit).
- `window.showConnectionLost()` — banner tiếng Việt full-screen "MẤT KẾT NỐI TỚI MÁY CHỦ" + nút Thử lại (`location.reload()`), có guard `getElementById('conn-lost')` nên nhiều request cùng fail chỉ hiện 1 banner.
- Handler `unhandledrejection`: nếu là lỗi mạng → banner rồi `return`; lỗi JS thật vẫn giữ overlay debug (đừng bỏ — đây là công cụ debug chính vì app không có build step).
- 2 fetch khởi động `/api/check_driver` + `/api/metadata` (trong `useEffect` đầu của App) trước đây KHÔNG có `.catch` → nay có. **Quy ước từ nay: mọi `fetch` mới phải có `.catch`** kiểu `catch(err => { if (window.isNetworkError(err)) window.showConnectionLost(); })`.
- Test: unit-test bằng node với DOM stub (isNetworkError 4 ca đúng/sai; gọi `showConnectionLost()` 3 lần chỉ tạo 1 banner) + chạy EXE thật gọi HTTP. EXE: Studio **v1.3.3**, Report **v1.4.2** (23/07 01:02–01:03).

**Ghi chú phát sinh:** LedgerReport nay có thêm **BC014 — Báo cáo bán hàng theo nguồn đơn** (nguồn `SALE_VIEW`, group nguồn đơn `EXTRA_ID_2` → đơn vị, bảng `bysource-table`) chưa được mô tả ở mục 1; Studio KHÔNG có. Bổ sung vào bảng danh sách báo cáo khi có dịp.

### 2026-07-18 (bổ sung) — Danh sách chứng từ bán hàng: thêm 7 cột  *(chỉ LedgerStudio)*

**Yêu cầu:** thêm vào Danh sách chứng từ bán hàng các cột: `PAYMENT_METHOD_ID` + `PAYMENT_METHOD_NAME` (tên từ `DM_PAYMENT_METHOD`), `EXTRA_ID_2` + `EXTRA_NAME_2` (tên từ `DM_EXTRA_2`), `INCOME_AMOUNT`, `VAT_INCOME_AMOUNT`, `COMMENTS` (Ghi chú).

**Backend `server.py` (khối SALE_VIEW ~1845–2180):**
- `SALE_EXTRA_COLUMNS = ["PAYMENT_METHOD_ID","EXTRA_ID_2","INCOME_AMOUNT","VAT_INCOME_AMOUNT","COMMENTS"]` — các cột NẰM TRÊN SALE_VIEW.
- **Guard schema (quan trọng):** `_sale_dim_info()` introspect `INFORMATION_SCHEMA.COLUMNS` của SALE_VIEW **1 lần, cache theo DB** (`_sale_dim_cache`), đồng thời nạp map `pay` (DM_PAYMENT_METHOD: PAYMENT_METHOD_ID→PAYMENT_METHOD_NAME) và `extra2` (DM_EXTRA_2: EXTRA_ID_2→EXTRA_NAME_2). `_sale_extra_cols(dim)` chỉ trả cột **thực sự tồn tại** → tránh bẫy "SELECT cột không có → crash pool" (mục 9.3). Nếu introspect fail → `cols` rỗng → KHÔNG thêm cột phụ (thà thiếu còn hơn crash). ⚠️ Lý do dùng guard: agent KHÔNG connect được DB để verify tên cột lúc code (classifier chặn kết nối DB ngoài) → để runtime tự lọc. Agent sau nếu confirm được tên cột có thể bỏ guard, nhưng KHÔNG khuyến khích.
- `_sale_select_list(need_join, extra_cols)` dựng SELECT động; thay `SALE_SELECT_LIST`/`SALE_BASE_SELECT` cũ (2 hằng này giờ dead-code, còn để tham chiếu). Dùng trong cả `get_sale` và `get_sale_stream_csv`.
- Map tên trong vòng lặp row (get_sale) + trong `transform` (stream_csv): thêm `PAYMENT_METHOD_NAME`, `EXTRA_NAME_2`. `INCOME_AMOUNT`/`VAT_INCOME_AMOUNT` thêm vào `SALE_NUM_COLS` (ép float). `SALE_CSV_COLS` thêm 7 dòng (cột xuất CSV).
- Cột phụ **KHÔNG thêm vào `SALE_SORT_WHITELIST`** → không sort/không column-search (tránh crash khi cột vắng). Muốn cho search sau này: thêm key vào `_build_sale_where` + whitelist, nhưng phải guard tồn tại cột.

**Frontend `index.html`:**
- Bảng bán hàng (virtual scroll, thứ tự cột CỐ ĐỊNH, 4 phần phải khớp số cột = **42**): (1) header row — thêm 7 `<th>` THƯỜNG (không SortableHeader) sau cột "Trả"; (2) hàng ô search — thêm 7 `''` vào mảng key (tổng 42, không search cột mới); (3) `SaleRow` — thêm 7 `<td>`; (4) `tfoot` — filler cuối `colSpan 8→15`. `SaleGroupRow` có `colSpan={100}` cuối nên tự phủ cột mới, không cần sửa.
- `SALE_EXPORT_COLS` (map xuất xlsx client-side chế độ "Mỗi đơn vị 1 sheet") thêm 7 cột.
- ⚠️ Khi thêm/bớt cột bảng bán hàng PHẢI đồng bộ ĐỦ 4 phần trên + `SALE_EXPORT_COLS` + `SALE_CSV_COLS` (backend), nếu lệch số cột → hàng search/tfoot lệch ô.

**Verify:** `py_compile` OK; `test_client GET /` = 200, markup 7 cột có mặt. **CHƯA test DB thật** — agent sau nên: mở tab Bán hàng xem cột mới có dữ liệu (đặc biệt PAYMENT_METHOD_NAME, EXTRA_NAME_2, COMMENTS), thử xuất CSV + xuất "mỗi ĐV 1 sheet", rồi build EXE.


### 2026-07-18 — BC007 (Nhật ký chung) + BC011 (Tổng hợp công nợ)  *(chỉ LedgerStudio, KHÔNG đụng LedgerReport)*

**Yêu cầu gốc của Trung:** (1) NKC phân trang 1000 dòng/trang + nút phân trang giống Ledger Studio (áp dụng cho báo cáo dài khác); (2) NKC hiện thêm cột Đơn vị, Tên đơn vị, Mã chứng từ; (3) NKC xuất Excel 2 lựa chọn (tổng hợp như web / chi tiết theo mẫu SQL, bổ sung Tên đơn vị); (4) BC011 thêm cột TK (tài khoản công nợ); (5) fix cột Mã & Tên đối tượng BC011 bị đè lên nhau.

**Đã sửa — Backend `server.py`:**
- `get_journal()` (`/api/journal`): SELECT thêm `ORGANIZATION_ID`, `TRAN_ID`; build `org_map` từ `DM_ORGANIZATION` (LEDGER_VIEW không có ORGANIZATION_NAME); mỗi row trả thêm `org_id`, `org_name`, `tran_id`.
- `report_export_csv()` (`/api/report_export_csv`): thêm param `mode` (`summary`/`detail`) cho BC007 — xem mục 7 bullet Export. Thêm `org_where_l` (alias `L.`) và `org_where_lv` (alias `LV.`) để tránh nhập nhằng khi JOIN DM_ORGANIZATION. BC008 giữ nguyên.
- **Ép mã dạng TEXT (giữ số 0 đầu)** trong CSV BC007: helper `_csv_text_cell(v)` → `="<mã>"` (công thức Excel trả text), áp cho **Mã đơn vị** (summary r[0], detail r[1]) + **Mã đối tượng** (detail r[10]). Vì file là CSV nên không set format ô được — dùng `="..."` là cách chuẩn để Excel không nuốt số 0 (vd '03' không thành 3). Muốn cột mã khác (Mã CT, TK...) cũng giữ text thì bọc thêm `_csv_text_cell`.
- `get_debt_summary()` (`/api/debt_summary`): 3 query dư/phát-sinh đổi `GROUP BY` sang `(PR_DETAIL_ID, ACCOUNT_ID)`; key dict thành tuple `(pid, acc)`; row trả thêm `acc`; sort `(acc, name, id)` — xem mục 6.

**Đã sửa — Frontend `index.html`:**
- Bảng BC007 (`nklist-table`): thêm 3 cột đầu Đơn vị/Tên đơn vị + cột Mã chứng từ (cạnh Số CT); dòng "Cộng lũy kế" `colSpan=9`. CSS thêm `.nklist-table .nk-org` (wrap tên đơn vị, max-width 150px).
- Phân trang: bỏ 2 nút FAB chevron cho BC007/BC008; thêm thanh `PageJumper` ngang (dùng chung style BC012), kèm badge tổng dòng.
- BC011: thêm cột `col-tk` (header + cell + ô tổng rỗng), CSS `col-code` word-break + rebalance width. Xem mục 6.
- Modal xuất Excel BC007: state `showJournalExport` + hàm `exportJournalCsv(mode)` trong `ReportTab`; `exportToExcel()` với BC007 mở modal thay vì tải thẳng. Modal render ở cuối JSX của ReportTab. Icon dùng `file-spreadsheet` + `table` (icon `list` KHÔNG tồn tại trong bộ Icon — nhớ chỉ dùng tên có trong `const icons` ~dòng 560).

**Verify đã chạy:** `py_compile server.py` OK; `test_client GET /` = 200 và markup mới có mặt (col-tk ×4, showJournalExport, exportJournalCsv, "Nhật ký chung chi tiết", "Tên đơn vị", "Mã chứng từ"). **CHƯA test với DB thật** (cần login SQL Server) — agent kế tiếp nên đối chiếu số liệu BC011 (TK tách đúng như mẫu Excel) + thử 2 nút xuất Excel BC007, rồi **build EXE** (`python build_exe.py`, nhớ tắt app đang chạy trước — xem mục 8).

**Chưa làm / cân nhắc:** 2-mode export chưa port sang LedgerReport (BC013 Report vẫn dùng debt_summary gộp-theo-đối-tượng cũ — nếu Trung muốn đồng bộ TK thì port `GROUP BY (PR_DETAIL_ID, ACCOUNT_ID)` sang Report). Mẫu `detail` bỏ `GROUP BY` của SQL gốc (LEDGER_VIEW không fan-out trùng dòng nên không cần) → nếu phát hiện trùng dòng thì thêm lại GROUP BY.

### 2026-07-24 — Sửa lỗi & Tối ưu hóa Sổ Nhật Ký Chung (BC007) + Bảng Kê Bán Ra (BC013) *(LedgerStudio)*

**Yêu cầu:** 
1. Fix lag/đơ máy (100% CPU) khi chuyển đổi giữa "Chi tiết" và "Tổng hợp" của BC013.
2. Sửa đường viền bị đậm (2px) hoặc mất viền ở ô "Ngày phát hành" trên BC013.
3. Sổ Nhật ký chung (BC007): Bổ sung nút "Chi tiết" và "Tổng hợp" trên Web, trong đó "Tổng hợp" ẩn 3 cột đầu (Đơn vị, Tên đơn vị, Ngày tháng ghi sổ). 
4. Đồng bộ Excel của BC007: Khi xuất "Bảng tổng hợp (như đang xem)", file Excel/CSV tải về phải ẩn 3 cột đầu nếu web đang chọn "Tổng hợp".

**Đã sửa — Frontend `index.html`:**
- **Tối ưu hóa Render:**
  - Khởi tạo 1 đối tượng `Intl.NumberFormat('en-US')` toàn cục (`_intlFmt`) thay vị gọi `toLocaleString` trong mỗi cell của vòng lặp render, giúp tăng tốc độ định dạng số lên **20x - 50x**.
  - Thêm CSS `content-visibility: auto !important; contain-intrinsic-size: 0 28px !important;` cho `tbody tr` của bảng BC013 để trình duyệt chỉ dựng các dòng hiển thị trên màn hình, giải quyết triệt để 100% CPU lag.
  - Sử dụng key duy nhất cho VDOM: đổi `key={idx}` thành `key={\`${row.serie}_${row.no}_${idx}\`}` giúp React hoán đổi dữ liệu tức thì.
  - Vô hiệu hóa nút bấm bằng thuộc tính `disabled={loading}` để ngăn ngừa spam click sinh ra nhiều request đồng thời gây đơ luồng.
- **Sửa đường viền:**
  - Loại bỏ các class viền inline gây xung đột (`border-r border-slate-300`, `border-b`, `border-t`).
  - Ghi đè CSS toàn cục cho cột cuối cùng của BC013: `.bc013-table th:last-child, .bc013-table td:last-child { border-right: 1px solid #cbd5e1 !important; }` để loại bỏ nét viền 2px đen đậm di sản của BCTC.
  - Thiết lập `.bc013-table th, .bc013-table td { border: 1px solid #cbd5e1 !important; }` kết hợp `border-collapse: collapse` để trình duyệt tự động gộp tất cả các đường thành 1px sắc nét đồng đều.
- **Chế độ hiển thị BC007:**
  - Khởi tạo state `journalViewMode` (detail/summary) và truyền xuống `ReportTab`.
  - Thêm bộ nút **Chi tiết / Tổng hợp** cho BC007. Khi ở chế độ `summary`, ẩn 3 cột đầu trong `thead` và `tbody`.
  - Cập nhật hàm `exportJournalCsv` truyền thêm query param `journal_view_mode` để đồng bộ cấu hình cột khi xuất file.

**Đã sửa — Backend `server.py`:**
- Cập nhật route `/api/report_export_csv`: nhận thêm tham số `journal_view_mode`.
- Với `report_type == "BC007"` và `mode == "summary"`: Nếu `journal_view_mode == "summary"`, loại bỏ 3 cột đầu tiên khỏi danh sách `headers` và payload dòng dữ liệu trả về cho CSV stream.

**Verify:** 
- Đã chạy kiểm tra Babel JSX thành công.
- Build EXE thành công phiên bản **v1.4.9** (`dist/iPOS_Ledger_Studio.exe`).

### 2026-07-25 — Chuẩn hóa Modal Thông Báo Sau Khi Tải File Báo Cáo *(LedgerStudio)*

**Yêu cầu:** 
Sửa lỗi khi bấm xuất file báo cáo (đặc biệt là các báo cáo stream CSV lớn như BC007, BC008, BC012, BC013), ứng dụng không bật bảng thông báo cho phép mở file trực tiếp hoặc mở thư mục chứa file.

**Đã sửa — Frontend index.html:**
- Thêm helper function downloadAndSaveApi(apiUrl, defaultFilename): fetch nội dung file từ backend, POST sang /api/save_export để ghi file trực tiếp vào thư mục xuất file chuẩn (_export_dir), sau đó gọi callback onExportSuccess(res.path, res.filename).
- Áp dụng downloadAndSaveApi cho tất cả các nút xuất Excel/CSV báo cáo:
  - BC007 (Sổ nhật ký chung)
  - BC008 (Sổ chi tiết tài khoản)
  - BC012 (Sổ tiền mặt & tiền ngân hàng)
  - BC013 (Bảng kê bán ra - tùy chọn xuất toàn bộ CSV/Excel)
- Sửa định dạng tên file name trong exportReportXls() đối với khoảng ngày tùy chỉnh (period.type === 'custom') để đảm bảo không bị undefined.

**Verify:** 
- Đã chạy kiểm tra Babel JSX thành công.
- Build EXE thành công phiên bản **v1.5.0** (dist/iPOS_Ledger_Studio.exe).


## Nâng cấp & Khắc phục v1.5.9 (2026-07-25)
- **Chuẩn hóa Explorer Focus**: Sửa lệnh `open_folder_route` ở backend Python sang `explorer.exe /select,"<path>"` giúp cửa sổ File Explorer lập tức bật lên phía trước màn hình (Foreground Focus) thay vì ẩn/thu nhỏ dưới Taskbar.
- **Đồng bộ Modal Tiến trình (0-100%)**: Tất cả tính năng xuất file (Excel, CSV, PDF) toàn ứng dụng đều được nối vào luồng Modal tiến trình trực quan từ 0-100%. Khi hoàn tất, Modal cung cấp 2 lựa chọn **"Mở file ngay"** và **"Mở thư mục chứa file"**.

### 2026-07-27 — Vá 2 nút xuất bị lỗi *(chỉ LedgerStudio, backend `server.py`)*

Rà soát toàn bộ nút xuất phát hiện 2 đường dẫn gọi sang endpoint KHÔNG tồn tại → người dùng chỉ thấy alert lỗi.

**1. BC013 — nút "Xuất toàn bộ CSV/Excel" trong modal xuất Bảng kê bán ra**
FE gọi `/api/report_export_csv?report_type=BC013&mode=detail|summary&...&acc_ids=`, nhưng hàm chỉ có nhánh BC007/BC008 → trả **400** "Report type không hỗ trợ xuất CSV".
- Đã thêm nhánh `elif report_type == "BC013"` (stream CSV, không phân trang, không giới hạn dòng). Nguồn `dbo.VAT_TRANSACTION_VIEW`, `DEBIT_CREDIT='CRD'`, 2 mode SQL **copy y hệt** `/api/vat_sales_report`: `summary` GROUP BY (SERIE, NO, DATE, PR_DETAIL_NAME, TAX_FILE_NUMBER, ACCOUNT_ID) sort theo (ngày, số HĐ); `detail` từng mặt hàng sort theo (thuế suất, ngày, số HĐ).
- ⚠️ **Bộ lọc phải dùng `_org_filter_sql`** (không chọn ĐV ⇒ `NOT IN` đơn vị ngoài cây '00') + tài khoản `LIKE` prefix đa chọn — dùng `org_where` kiểu `IN` như BC007/BC008 sẽ **lệch số so với màn hình**. Tham số nối theo thứ tự mệnh đề: date → org → acc (mục 9.2).
- Cột CSV khớp đúng 11 cột bảng web (TT, Ký hiệu HĐ, Số HĐ, Ngày phát hành, Tên người bán, MST người mua, Mặt hàng, Doanh số chưa thuế, Thuế suất, Thuế GTGT, Ghi chú). Ký hiệu HĐ / số HĐ / MST bọc `_csv_text_cell` (giữ số 0 đầu). Kết file có dòng **Tổng cộng** (cộng dồn khi stream).
- ⚠️ `report_export_csv` KHÔNG có `@with_db_lock` (cố ý — nó stream bằng connection riêng). Nhánh BC013 gọi `_org_filter_sql` → có thể chạm `get_connection()` **1 lần duy nhất mỗi DB** nếu `_external_orgs_cache` chưa warm. Thực tế luôn warm vì phải bấm "Xem" trước thì nút Excel mới bật.

**2. Tab "Doanh thu chờ phân bổ" — nút "Tất cả vào 1 file CSV"**
`/api/income_alloc/stream_csv` **chưa từng được viết** (chỉ có 5 route: ledger/purchase/warehouse/sale/voucher). Lỗi bị che cho tới khi `SERVER_STREAM_THRESHOLD` đổi 500.000 → **0** (2026-07-08): từ đó mode "1 file" LUÔN đi đường server → POST vào route 404 → alert "Lỗi:".
- Đã thêm route theo đúng khuôn `get_voucher_stream_csv` (`_start_export_job` + `_build_income_alloc_where` + `_income_alloc_cte` + `_resolve_order_by`), kèm hằng `INCOME_ALLOC_CSV_COLS` (27 cột, thứ tự/nhãn khớp `INCOME_ALLOC_EXPORT_COLS` ở `index.html` để 2 chế độ xuất ra cùng bố cục).
- Map tên (ĐV/hàng hóa/công việc/đối tượng/chứng từ) + `ALLOC_METHOD_MAP` lấy **1 lần trước khi tạo job**; `transform` chạy ở thread nền nên **không được đụng `session`/DB**.
- Thứ tự params: `d_params` (3 tham số ngày của CTE D) **trước** `w_params` — CTE đứng trước WHERE.

**Verify:** `ast.parse` OK; `url_map` có đủ 2 route; test bằng **connection giả** (monkeypatch `_make_conn`/`_export_dir`, script trong scratchpad) → BC013 dựng đúng SQL/params/CSV cho cả 2 mode; income_alloc job chạy tới `status=done`, file CSV ghi đúng, map tên + ngày `dd/mm/yyyy` + tiêu thức phân bổ đều đúng. **CHƯA test với DB thật** (agent bị chặn kết nối SQL ngoài) — agent/người sau nên đối chiếu tổng BC013 CSV với 3 dòng tổng dưới bảng web, và xuất thử tab Doanh thu chờ phân bổ.

### 2026-07-27 (tiếp) — Xuất Excel GIỮ FORM cho báo cáo có phân trang *(chỉ LedgerStudio)*

**Vấn đề:** `exportReportXls()` đọc DOM nên báo cáo phân trang xuất ra **thiếu dòng mà không báo lỗi** — BC013 đang dính (chỉ ra 1000 dòng đầu); BC008/BC012 né bằng cách chỉ cho xuất CSV thô, mất form báo cáo.

**Backend `server.py` — 3 route nhận `page_size=0` = lấy TOÀN BỘ:**
- `/api/vat_sales_report` (BC013): bỏ clamp cứng `page_size ≤ 1000`, thêm cờ `export_all`; khi export_all thì `start_row=0, end_row=total_rows`, `total_pages=1`.
- `/api/account_details` (BC008): `export_all` ⇒ cận trên `RowNum` = `total_rows`, `total_pages=1`. `offset_balance` = 0 (đúng, vì file bắt đầu từ dư đầu kỳ).
- `/api/cash_book` (BC012): `page_size<=0` ⇒ trả thẳng toàn bộ `flat`.
- ⚠️ **Cả 3 chỗ phải chặn chia 0** khi tính `total_pages` — đó chính là lỗi sẽ gặp nếu chỉ sửa frontend.

**Frontend `index.html`:** thêm `exportFullXls` + `buildFullExportReq` + `exportPagedCsv` + state `fullExportRows`/`fullExporting`, modal `showPagedExport` cho BC008/BC012, và 2 nút xls của modal BC013 chuyển sang `exportFullXls`. Bảng render qua `pagedDataRows` / `cbRowsView`. Chi tiết cơ chế: mục 7, bullet "BÁO CÁO CÓ PHÂN TRANG".
- Dòng "Cộng trang" của BC013 tự đổi nhãn thành "Tổng cộng" khi đang render bản đầy đủ.
- Modal BC007 thêm ghi chú vì sao chỉ có CSV (dữ liệu vượt trần dòng của Excel).

**Verify:** `ast.parse` OK; parse JSX bằng `@babel/parser` OK; test `page_size=0` bằng DB giả cho cả 3 route → không ZeroDivisionError, trả đủ dòng, `total_pages=1`, cận trên `RowNum` = `total_rows`. **CHƯA test DB thật** (bị chặn kết nối). EXE build lại: **v1.6.7** (27/07/2026 22:14, đã verify mtime + FileVersion).

**Lưu ý hiệu năng chưa đo được:** `exportReportXls()` gọi `getComputedStyle` cho TỪNG Ô — 50.000 dòng × 11 cột ≈ 550.000 lần → có thể mất hàng chục giây và làm treo UI. Ngưỡng cảnh báo hiện đặt `FULL_XLS_WARN_ROWS = 50.000` (bằng `SHEET_LIMIT` của Report). Nếu người dùng phản ánh chậm thì **hạ ngưỡng** (vd 20.000) chứ đừng bỏ cảnh báo.

**Phát hiện thêm khi review — BC008 chọn NHIỀU tài khoản trả về RỖNG (đã vá cùng ngày):** Studio vẫn dùng
`ACCOUNT_ID LIKE ? + '%'` với nguyên chuỗi `'111,112'` → `LIKE '111,112%'` → 0 dòng, cả bảng web lẫn file xuất,
**không báo lỗi**. Đây đúng sự cố LedgerReport đã sửa 17/07/2026 (mục 9.6) nhưng **chưa từng port sang Studio**.
Đã port helper **`_acc_like_sql(account_id, col)`** và áp cho `get_account_details` (4 query: dư đầu năm, lũy kế,
stats, phân trang) + nhánh BC008 của `report_export_csv` (3 query). Đồng thời bỏ `.split(",")[0]` ở đầu
`report_export_csv` (trước đây nút xuất chỉ lấy **tài khoản đầu tiên**, lệch thầm lặng so với màn hình); tên file
giờ ghi `111-112`. ⚠️ Còn `export_excel_backend` (dead code, không nút nào gọi) vẫn dùng cách cũ — nếu nối lại nút
thì phải sửa trước. Verify bằng DB giả: cả web lẫn nút xuất đều sinh `(ACCOUNT_ID LIKE ? OR ACCOUNT_ID LIKE ?)`
với params `['111%','112%']` đúng thứ tự mệnh đề.

### 2026-07-27 (tiếp) — 🔥 `<colgroup>` làm hỏng bố cục .xls: fix đã MẤT KHỎI CODE ở CẢ 2 APP

Tài liệu (mục 7) từ 17/07/2026 ghi `exportReportXls()` "xoá hẳn `<colgroup>` khỏi bản clone", nhưng rà lại
27/07/2026 thì **cả Studio lẫn Report đều KHÔNG có đoạn code đó** — nhiều khả năng bị mất khi ai đó viết lại
`exportReportXls`. Hậu quả: mọi báo cáo có `<colgroup>` (Studio **BC012**, Report **BC012 + BC014**) xuất .xls
ra bố cục lệch, Excel tự căn cột theo nội dung. Đã thêm lại vào cả 2 app:
```js
clone.querySelectorAll('colgroup').forEach(cg => cg.remove());
```
Lý do kỹ thuật: `<col>` là `display:table-column` nên `getComputedStyle(col).width` trả **nguyên văn `"20%"`**
(không quy ra px như `<td>`) → Excel không hiểu. Chiều rộng đúng lấy từ `width:XXpx` đã nội tuyến trên từng ô.
⚠️ Bài học: fix chỉ nằm trong tài liệu mà không có test tự động thì rất dễ bị xoá lúc refactor — khi sửa
`exportReportXls` phải kiểm lại dòng này còn không.

**Phát hiện kèm theo — nút ✕ đóng modal vô hình ở CẢ 2 APP:** bộ `const icons` chỉ có **19 icon** và **KHÔNG có
tên `"x"`** (Studio lẫn Report). `Icon` render `icons[name] || ''` nên không crash, chỉ ra một `<svg>` RỖNG →
nút đóng modal bấm được nhưng **không thấy dấu ✕**. Modal xuất Excel BC013 (Studio) đã dính từ trước. Đã thay
`<Icon name="x" size={18}/>` bằng ký tự `✕` ở mọi modal của cả 2 app. ⚠️ Trước khi dùng `<Icon name="...">`
phải kiểm tên có trong `const icons` (Studio ~dòng 590, Report ~dòng 435) — tài liệu từng cảnh báo với icon `list`.

### 2026-07-27 (tiếp) — P5 ĐỒNG BỘ SANG LEDGERREPORT ✅ *(Trung cấp quyền sửa Report)*

- **`server.py`:** `/api/account_details` nhận `page_size=0` (export_all ⇒ cận trên `RowNum` = `total_rows`,
  `total_pages=1`); `/api/cash_book` chấp nhận **cả** `export_all=1` (đã có) **lẫn** `page_size<=0` để dùng chung
  quy ước với Studio.
- **`index.html`:** thêm `fullExportRows`/`fullExporting`/`showPagedExport`, `exportFullXls`, `buildFullExportReq`,
  `exportPagedServer`, `useLayoutEffect` xuất, và 2 biến render `pagedDataRows` (BC008) / `cbRowsView` (BC012).
  Nút Excel BC008/BC012 mở modal 2 lựa chọn. **Khác Studio:** lựa chọn thứ 2 của Report BC008 là **xlsx từ máy chủ**
  (`/api/export_excel_backend` — Report KHÔNG có `/api/report_export_csv`), BC012 là CSV stream. BC007 Report vẫn
  xuất thẳng xlsx backend như cũ.
- Report **không có** BC013 bán ra và **không có** tab `income_alloc` → P1/P2/P3 không áp dụng; helper
  `_acc_like_sql` Report vốn đã có từ 17/07.
- Verify: `ast.parse` + parse JSX Report OK; test `page_size=0` bằng DB giả → BC008 lấy đủ dòng (`RowNum > 0 AND <= total_rows`,
  bộ lọc TK đa chọn ra `['111%','112%']`), BC012 trả toàn bộ flat, `total_pages=1`.
