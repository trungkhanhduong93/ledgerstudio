# Hướng dẫn triển khai báo cáo BC007 – BC010 (LedgerReport → LedgerStudio)

> Tài liệu handoff để port các báo cáo từ **LedgerReport** sang **LedgerStudio**.
> Tự chứa — đọc file này là đủ, không cần lịch sử chat. Mọi `file:line` tham chiếu theo `server.py` / `index.html` của **LedgerReport** (bản đã validated 24/06/2026).

---

## 0. Kiến trúc & bối cảnh

- **Backend:** Flask single-file `server.py`. Mỗi báo cáo = 1 route `@app.route("/api/...")` bọc `@with_db_lock`, đọc `from_date`/`to_date` (dạng `dd/mm/yyyy`), `org_ids` (CSV).
- **Frontend:** React single-file `index.html` (Babel in-browser). Báo cáo khai trong mảng `REPORT_TYPES`; mỗi loại có nhánh **fetch** trong `loadReportData()` và nhánh **render** trong chuỗi ternary của bảng `.report-table`.
- **Đóng gói:** `BuildEXE.bat` (PyInstaller one-file). Build thủ công:
  ```
  python -m PyInstaller --noconsole --onefile --clean --noconfirm --name "iPOS_Accounting_Report" --icon icon.ico --add-data "index.html;." --add-data "install_driver.ps1;." --add-data "manifest.json;." --add-data "icon.svg;." --collect-submodules flask --collect-submodules flask_cors --collect-submodules pyodbc --hidden-import pyodbc --hidden-import flask --hidden-import flask_cors server.py
  ```

### Bảng LEDGER — các cột quan trọng (SQL Server)
| Cột | Ý nghĩa |
|---|---|
| `ACCOUNT_ID` | Tài khoản của bút toán (1 leg) |
| `ACCOUNT_ID_CONTRA` | **Tài khoản đối ứng** (luôn có giá trị) — mấu chốt cho LCTT trực tiếp |
| `DEBIT_CREDIT` | `'DEB'` / `'CRD'` |
| `AMOUNT` | Số tiền (decimal) |
| `TRAN_DATE` | **smalldatetime** (KHÔNG phải varchar). So sánh bằng chuỗi `'YYYYMMDD'` vẫn đúng |
| `TRAN_NO`, `TRAN_ID`, `DESCRIPTION`, `ORGANIZATION_ID`, `PR_DETAIL_ID` | … |

LEDGER lưu kiểu đối ứng kép: mỗi nghiệp vụ Dr X/Cr Y tạo 2 dòng (1 dòng `ACCOUNT_ID=X DEB contra Y`, 1 dòng `ACCOUNT_ID=Y CRD contra X`). Tổng theo `ACCOUNT_ID` (DEB−CRD) = số dư.

### Đặc điểm dữ liệu DB `IACC_CHULONG` (để kiểm thử)
- LEDGER **bắt đầu từ 2026-01-01**, `BALANCE_VIEW` **trống** → số dư đầu năm 2026 = 0. Bút toán mô tả *"Điều chỉnh mang về tổng tháng 1"* ngày 1/1 chính là số dư đầu kỳ hạch toán thành phát sinh ⇒ tháng 1 "tiền đầu kỳ" = 0 là ĐÚNG.
- Công ty **kết chuyển P&L hàng tháng** sang 911→421 ⇒ net TK 5/6/7/8 ≈ 0 nếu KHÔNG loại bút toán đối ứng `911`.
- Bộ lọc đơn vị: `_org_filter_sql` mặc định **loại đơn vị ngoài cây '00'** (vd org `'66'`) khi không chọn đơn vị nào.

### Helpers dùng chung (server.py)
- `_org_filter_sql(org_ids, col)` → `(clause, params)`. Không chọn ⇒ `col NOT IN (đơn vị ngoài)`.
- `_calc_results(data, thtt_expense_list, expense_classes)` → dict KQKD; **`r['13']` = LN trước thuế**, `r['07']` = chi phí tài chính (lãi vay). Loại bút toán đối ứng `911`/`521`. `r['13']` chỉ phụ thuộc tổng TK 5/6/7/8 nên truyền `item_class/expense=''` vẫn đúng.
- `_map_account_to_cdkt(acc, bal)` / `_calc_cdkt_balances(rows)` → quy đổi TK ra mã CĐKT (dùng cho BC005, không bắt buộc cho BC007–BC010).

---

## 1. BC007 — SỔ NHẬT KÝ CHUNG (S03a-DN)

- **Endpoint:** `GET /api/journal` — `get_journal()` (server.py ~2994).
- **Nguồn:** `dbo.LEDGER_VIEW` (KHÔNG phải LEDGER). Phân trang bằng `ROW_NUMBER() OVER (ORDER BY TRAN_DATE, TRAN_NO)`.
- **Tham số:** `from_date, to_date, org_ids, page, page_size` (mặc định page_size=10000).
- **Org filter:** dùng `_org_filter_sql(org_ids, "ORGANIZATION_ID")` → **mặc định loại đơn vị ngoài cây '00' (vd '66')**, đồng bộ với các báo cáo khác. (Lưu ý: bản gốc từng tự viết `if org_ids: IN(...)` nên KHÔNG loại 66 — đã sửa 25/06/2026; khi port nhớ dùng `_org_filter_sql`.)
- **Trả về:**
  ```json
  { "status":"ok",
    "data":[{tran_date,tran_no,description,account_id,contra_account_id,debit_credit,amount,
             org_id,org_name,tran_id}],
    "period_sums":{"deb":..,"crd":..},
    "pagination":{"total_rows":..,"total_pages":..,"page":..} }
  ```
- **Logic:** 1 query COUNT + tổng DEB/CRD; 1 query CTE lấy trang (`RowNum > offset AND <= offset+page_size`). offset = (page−1)*page_size.
- **Frontend:** dữ liệu lớn ⇒ export từ backend, không export DOM. Render dạng bảng nhật ký, có phân trang.

> **⚠️ CẬP NHẬT 18/07/2026 (chỉ LedgerStudio) — xem chi tiết ở `KIEN_TRUC_TOAN_TAP.md` mục 13:**
> - Endpoint trả THÊM `org_id`, `org_name` (map từ `DM_ORGANIZATION`), `tran_id`. Bảng web hiện thêm 3 cột **Đơn vị / Tên đơn vị / Mã chứng từ**.
> - **Phân trang cố định 1000 dòng/trang**, nút phân trang là thanh `PageJumper` ngang (giống BC012), KHÔNG còn "Tải thêm"/FAB chevron.
> - **Xuất Excel 2 kiểu** qua modal → `/api/report_export_csv?report_type=BC007&mode=summary|detail` (summary = như web + ĐV/Tên ĐV/Mã CT; detail = nhật ký chung chi tiết theo mẫu SQL, có Tên đơn vị JOIN từ DM_ORGANIZATION).
> - Số dòng thực tế ~600k/tháng → dùng CSV stream; xls/xlsx không chứa nổi cả năm (giới hạn 1.048.576 dòng/sheet).

---

## 2. BC008 — SỔ CHI TIẾT TÀI KHOẢN

- **Endpoint:** `GET /api/account_details` — `get_account_details()` (server.py ~3070).
- **Bắt buộc tham số `account_id`** (lọc `ACCOUNT_ID LIKE account_id + '%'`).
- **Org filter:** dùng `_org_filter_sql` → mặc định loại '66' (đã sửa 25/06/2026, giống BC007).
- **Nguồn:** `BALANCE_VIEW` (số dư đầu năm) + `LEDGER_VIEW` (phát sinh).
- **Số dư đầu kỳ** = số dư đầu năm (BALANCE_VIEW tại `first_day_of_year`) **+** phát sinh lũy kế từ đầu năm đến `from_date` (nếu from_date > 1/1).
- **offset_balance:** số dư đến đầu trang (phục vụ phân trang đúng số dư lũy kế).
- **Trả về:** `opening_balance{deb,crd}`, `offset_balance{deb,crd}`, `period_sums{deb,crd}`, `data[{tran_date,tran_no,description,contra_account_id,debit_credit,amount}]`, `pagination`.
- **Số dư cuối kỳ** (tính ở frontend) = đầu kỳ + Σphát sinh DEB − Σphát sinh CRD (theo tính chất TK).

---

## 3. BC009 — LƯU CHUYỂN TIỀN TỆ, PHƯƠNG PHÁP TRỰC TIẾP (B03-DN)

- **Endpoint:** `GET /api/cash_flow` — `get_cash_flow()` (server.py ~2330). **Trả CẢ BC009 và BC010**: `{"data":{"direct":{...}, "indirect":{...}}}`. BC009 dùng `direct`, BC010 dùng `indirect`.
- **Cơ chế trực tiếp:** quét mọi "leg tiền" (TK `111/112/113/1281`) trong kỳ, phân loại theo **`ACCOUNT_ID_CONTRA`**:
  ```sql
  SELECT ACCOUNT_ID_CONTRA, DEBIT_CREDIT, SUM(AMOUNT)
  FROM dbo.LEDGER WITH (NOLOCK)
  WHERE (ACCOUNT_ID LIKE '111%' OR '112%' OR '113%' OR '1281%')
    AND TRAN_DATE BETWEEN from AND to [AND org]
  GROUP BY ACCOUNT_ID_CONTRA, DEBIT_CREDIT
  ```
  - **Loại trừ** leg có contra cũng là tiền (`_cf_is_cash`) — đó là chuyển nội bộ giữa các TK tiền (111↔112↔113).
  - `DEB` = tiền THU (+), `CRD` = tiền CHI (−).
- **Hàm phân loại `_cf_classify_direct(contra, dc)`** → mã chỉ tiêu (quy ước đã chốt với nghiệp vụ Chú Long):
  | Chiều | Contra | Mã | Ý nghĩa |
  |---|---|---|---|
  | THU | 511,512,131, 3331 | **01** | thu bán hàng, thu nợ KH, VAT đầu ra |
  | THU | 411 | 31 | nhận vốn góp CSH |
  | THU | 3411,341,343,171 | 33 | thu đi vay |
  | THU | 515,1281,1288,1283,121 | 27 | thu lãi, cổ tức |
  | THU | 128 | 24 | thu hồi cho vay |
  | THU | 221,222,2281 | 26 | thu hồi góp vốn |
  | THU | 711 | 22 | thanh lý TSCĐ |
  | THU | (còn lại) | 06 | thu khác HĐKD |
  | CHI | 131 | **01** | đảo/hoàn thu bán hàng → net Mã 01 |
  | CHI | 334 | 03 | trả người lao động |
  | CHI | 3334 | 05 | thuế TNDN |
  | CHI | 635 | 04 | lãi vay đã trả |
  | CHI | 15x,331,611,621,627,641,642,133,242,142 | 02 | chi NCC/HHDV |
  | CHI | 211,213,217,241 | 21 | mua TSCĐ |
  | CHI | 128 | 23 | chi cho vay |
  | CHI | 221,222,2281 | 25 | chi góp vốn |
  | CHI | 3412 | 35 | nợ gốc thuê TC |
  | CHI | 3411,341,343,171 | 34 | trả nợ gốc vay |
  | CHI | 419 | 32 | mua lại cổ phiếu |
  | CHI | 421 | 36 | cổ tức đã trả |
  | CHI | (còn lại) | 07 | chi khác HĐKD |
- **Tổng hợp:** `20=Σ(01..07)`, `30=Σ(21..27)`, `40=Σ(31..36)`, `50=20+30+40`.
- **Tiền đầu/cuối kỳ:** `60` = số dư tiền đầu kỳ (BALANCE_VIEW đầu năm + ledger trước from), `70` = đến to. `61` (ảnh hưởng tỷ giá) = 0.
- **Số kiểm soát:** `50` **phải** = net biến động tiền thực tế = `70 − 60`. (T1/2026 = **6,166,411,252**, chênh 0.)

---

## 4. BC010 — LƯU CHUYỂN TIỀN TỆ, PHƯƠNG PHÁP GIÁN TIẾP (B03-DN, chuẩn TT200)

- Cùng endpoint `/api/cash_flow`, nhánh `indirect`.
- **Mã 01 LN trước thuế:** GỌI THẲNG `_calc_results(cf_data, {}, {})['13']`. ⚠️ **KHÔNG tự viết công thức rút gọn** (bản rút gọn từng sai 4.76 tỷ vs 1.35 tỷ thật do bỏ giảm trừ 521 & xử lý 511/641/642 sai).
- **Điều chỉnh:** `02` khấu hao = `s('214','CRD',['911']) − s('214','DEB',['911'])`; `03` dự phòng (229,352,159); `06` lãi vay = `r['07']`; `04`,`05` = 0.
- **Thay đổi vốn lưu động** (net phát sinh kỳ, loại 911): `09` phải thu (131,133,136,138,141,244); `10` tồn kho (15x); `11` phải trả (331,333,334,335,336,337,338); `12` chi phí trả trước (242); `13` chứng khoán KD (121). Quy ước dấu: tài sản tăng ⇒ (−), nợ tăng ⇒ (+).
- **`14` lãi vay đã trả, `15` thuế TNDN đã nộp** = lấy từ trực tiếp (`d['04']`, `d['05']`).
- **Mã 07 "Các khoản điều chỉnh khác" = PLUG**: `07 = d['20'] − (base + ΣWC)` để **Mã 20 gián tiếp khớp tuyệt đối Mã 20 trực tiếp**. ⚠️ Plug T1 lớn (~4 tỷ) do bút toán "mang về" số dư đầu kỳ ngày 1/1; từ T2 nhỏ hơn.
- **HĐĐT/HĐTC/50/60/70** dùng chung với trực tiếp.
- **Kiểm thử T1/2026:** Mã 01 = **1,349,796,031**, Mã 20 = **3,590,845,737** (= trực tiếp).

> **Lưu ý đối chiếu Bảng CĐKT:** Mã 01 (BC001 r13 = 1,349,796,031) lệch **56,580,000** so với biến động TK 421 trên BC005 (1,293,216,031). Nguyên nhân: **lỗi nhập liệu** — bút toán kết chuyển 641→911 của đơn vị org=74 ("CPMCL-NTRA-01 Trần Nhật Duật") thừa 56,580,000 so với chi phí thực (TK 6411 dư Có sau kết chuyển). KHÔNG phải lỗi code.

---

## 6. Tích hợp Frontend (index.html) — checklist cho mỗi báo cáo

1. **`REPORT_TYPES`**: thêm `{ id:'BCxxx', name:'...' }`.
2. **Mảng chỉ tiêu** (với báo cáo dạng cố định): `CF_DIRECT_INDICATORS`, `CF_INDIRECT_INDICATORS` — mỗi phần tử `{id, name, type}` với `type ∈ section|group|item|total|plain`.
3. **`loadReportData()`**: thêm nhánh `else if (reportType === 'BCxxx')` → `fetch('/api/...')` → `setReportData(...)`; nhớ `setMonthList([]); setMonthlyData({}); setJobList([]); setJobData({})`.
4. **Render** (chuỗi ternary của `.report-table`): BC009/010 dùng chung 1 nhánh `(reportType==='BC009'||'BC010')`, chọn mảng chỉ tiêu tương ứng; cột "Kỳ này" đọc `reportData[row.id]`. Dòng `id` rỗng = tiêu đề (không in giá trị).
5. **Tiêu đề** (`<h1>`) + **nhãn mẫu** (`Mẫu B03 - DN`) + **tên file export** (`a.download`): thêm điều kiện cho BCxxx.
6. **Export Excel/PDF**: BC009/010 dùng export DOM (`exportToExcel` clone `.report-table`) — tự chạy, chỉ cần thêm tên file.

---

## 7. Quy trình sau khi port sang LedgerStudio

1. Copy logic endpoint + helper (`_calc_results`, `_cf_classify_direct`, `_cf_is_cash`) vào `server.py` của LedgerStudio.
2. Copy mảng chỉ tiêu + các nhánh frontend vào `index.html`.
3. **Kiểm thử đối chiếu** với DB `IACC_CHULONG` (T1 & T2/2026) theo các số mốc ở trên — đặc biệt:
   - BC009: `50 == 70−60` (T1 = 6,166,411,252).
   - BC010: `20 indirect == 20 direct`.
4. Build EXE, chạy thử.

---

## 8. DANH SÁCH CHỨNG TỪ (list lớn) — pattern & công thức cho **Danh sách chứng từ BÁN HÀNG**

> Khác hẳn BC005–BC010 (báo cáo tài chính layout cố định, vài chục dòng). "Danh sách chứng từ" = **bảng dữ liệu lớn** (vài trăm nghìn → triệu dòng): phân trang server-side, virtual scroll, tìm kiếm theo cột, xuất Excel/CSV dạng streaming. Các list hiện có: **Ledger** (`/api/ledger`), **Mua hàng** (`/api/purchase`, nguồn `PURCHASE_VIEW`), **Kho** (`/api/warehouse`, `WAREHOUSE_VIEW`).

### 8.1. Mỗi danh sách = 3 endpoint
| Endpoint | Vai trò |
|---|---|
| `/api/<name>` | Lấy 1 trang (`page`, `page_size`) + tổng (COUNT, SUM các cột tiền) |
| `/api/<name>/count` | Chỉ đếm tổng dòng + tổng tiền (khi cần riêng) |
| `/api/<name>/stream_csv` (POST/GET) | Tạo **export job** chạy nền → trả `job_id`; FE poll `/api/export/status` |

### 8.2. Khung backend (theo mẫu `get_purchase`, server.py ~984 — đơn giản nhất, 1 VIEW)
1. **Đọc tham số:** `page`, `page_size` (mặc định 100), `export_all`, và `known_total`/`known_sums` (để **skip COUNT khi đổi trang** — tối ưu tốc độ: `skip_count = page>1 and known_total and not export_all`).
2. **WHERE động:** hàm `_build_<name>_where(args)` → `(where_sql, params)`. Luôn bắt đầu bằng `TRAN_DATE >= ? AND TRAN_DATE <= ?` (`from_date`/`to_date` dạng dd/mm/yyyy → `.strftime('%Y%m%d')`). Thêm:
   - **IN filter** đa chọn: `org_ids`, `job_ids`, `item_ids`, `expense_ids`, `pr_detail_ids`, `wh_ids`, `tran_ids` (CSV → `field IN (?,?..)`).
   - **TK cha→con:** `acc_ids`/`contra_acc_ids` dùng `LIKE 'xxx%'` (chọn 641 ⇒ khớp 6411..6419), SARGable.
   - **Search theo cột:** ID dùng `LIKE 'val%'` (trailing wildcard — dùng index); TEXT (mô tả) dùng `LIKE '%val%'`; ngày dùng `_apply_date_search` (parse dd/mm/yyyy, mm/yyyy, yyyy… thành filter SARGable).
   - **Search theo cột TÊN** (cần JOIN dimension): trả riêng `join_clauses/join_params`, chỉ JOIN bảng cần (DM_ORGANIZATION, DM_EXPENSE, DM_ITEM…) — xem `get_ledger` server.py ~615.
3. **ORDER BY an toàn:** `_resolve_order_by(args, <NAME>_SORT_WHITELIST, default)` — chỉ cho sort theo cột trong **whitelist** (chống SQL injection). Whitelist = `{col: "P.col"}` + map cột tên (`ORGANIZATION_NAME → O.ORGANIZATION_NAME`).
4. **Phân trang ROW_NUMBER** (tương thích SQL Server 2008, KHÔNG dùng OFFSET/FETCH):
   ```sql
   SELECT * FROM (
     SELECT {cols}, ROW_NUMBER() OVER (ORDER BY {order_by}) AS RowNum
     {FROM ... JOIN ...} WHERE {where}
   ) X WHERE RowNum > ? AND RowNum <= ?   -- params: offset, offset+page_size
   ```
5. **Tổng tiền:** `SELECT COUNT(*), SUM(ISNULL(col,0))... WHERE {where}` (riêng query, bỏ khi skip_count).
6. **export_all=1:** bỏ phân trang, `SELECT ... ORDER BY` toàn bộ (chỉ dùng cho tập nhỏ; tập lớn dùng stream_csv).
7. **Map tên dimension ở Python** từ `_meta_cache` (tránh JOIN khi không search tên) — nhanh nhất.
8. Khai **`<NAME>_BASE_COLUMNS`** (list cột lấy ra) + **`<NAME>_SORT_WHITELIST`** + **`<NAME>_CSV_COLS`** (`[(col, "Nhãn tiếng Việt")]` cho export) ở cấp module.

### 8.3. Export streaming (file lớn)
- `/api/<name>/stream_csv` gọi `_start_export_job(filename, headers, sql, params, transform_row, total_estimate)` (server.py ~1524): mở **connection riêng** (không dùng pool), `fetchmany(1000)`, ghi `.xlsx`/`.csv` ra đĩa ở **thread nền**, trả `job_id` ngay.
- FE poll **`GET /api/export/status?job_id=`** → `{status, current, total, file_path}`; xong thì mở bằng `/api/open_file`. Hủy: `/api/export/cancel`.
- `transform_row(raw, sql_cols)` map theo thứ tự `<NAME>_CSV_COLS`.

### 8.4. Frontend (copy từ nhánh Ledger/Purchase trong index.html)
- **REPORT_TYPES:** thêm `{id:'BC0xx', name:'DANH SÁCH CHỨNG TỪ BÁN HÀNG'}`.
- **State + fetch:** lưu `data`, `total`, `summary`; truyền lại `known_total`/`known_sums` khi đổi trang để skip COUNT.
- **Virtual scroll** (`useMemo` + cửa sổ render) cho bảng lớn — bắt buộc, tránh crash RAM.
- **Ô search theo cột** (debounce ~300ms) → set vào query (`s_desc`, `s_acc_id`, `s_item_name`…); đổi search ⇒ reset `page=1`, bỏ `known_total`.
- **Sort cột:** set `order_by`/`order_dir` (chỉ cột có trong whitelist).
- **Export:** nút Excel → POST `/api/<name>/stream_csv` → nhận `job_id` → poll status → mở file. (KHÔNG export DOM cho list lớn.)

### 8.5. ✅ Công thức cho **DANH SÁCH CHỨNG TỪ BÁN HÀNG** (LedgerStudio)
- **Nguồn:** `dbo.SALE_VIEW` (đã có sẵn, 152 cột, mức **dòng hàng/chi tiết** — mỗi mặt hàng 1 dòng; đã kèm `ITEM_NAME`, `JOB_NAME`, `PR_DETAIL_NAME`, `ORGANIZATION_ID`). Tên DM khác lấy qua JOIN `DM_ORGANIZATION` / `DM_EXPENSE` như Purchase. (`SALE` = bảng gốc header; `SALE_DETAIL` = chi tiết — nhưng **`SALE_VIEW` đã gộp sẵn**, dùng nó cho tiện.)
- **Alias `S.`**. Filter ngày: `S.TRAN_DATE` (smalldatetime).
- **`SALE_BASE_COLUMNS`** (đề xuất — chứng từ bán hàng):
  ```
  ORGANIZATION_ID, TRAN_ID, TRAN_NO, TRAN_DATE,
  VAT_TRAN_NO, VAT_TRAN_DATE, VAT_TRAN_SERIE,
  PR_DETAIL_ID, PR_DETAIL_NAME,            -- khách hàng (mã/tên)
  CONTACT_PERSON, ADDRESS, TAX_FILE_NUMBER, PHONE,
  WAREHOUSE_ID, EMPLOYEE_ID,
  ITEM_ID, ITEM_NAME, DESCRIPTION, UNIT_ID,
  QUANTITY, UNIT_PRICE, AMOUNT,            -- SL, đơn giá, thành tiền (trước thuế)
  DISCOUNT_AMOUNT, VAT_TAX_RATE, VAT_TAX_AMOUNT,
  TOTAL_AMOUNT,                            -- tổng thanh toán
  COG_AMOUNT,                              -- giá vốn (lãi gộp = AMOUNT - COG_AMOUNT)
  ACCOUNT_ID, ACCOUNT_ID_INCOME, ACCOUNT_ID_VAT,
  EXPENSE_ID, JOB_ID, JOB_NAME, IS_RETURN, STATUS
  ```
- **`SALE_SORT_WHITELIST`** = `{col: f"S.{col}"}` cho các cột trên + `ORGANIZATION_NAME→O.ORGANIZATION_NAME`. Default: `"S.TRAN_DATE DESC, S.TRAN_NO"`.
- **Tổng tiền (SUM):** `QUANTITY, AMOUNT, DISCOUNT_AMOUNT, VAT_TAX_AMOUNT, TOTAL_AMOUNT, COG_AMOUNT`.
- **`_build_sale_where`:** copy `_build_purchase_where`, đổi alias `P.`→`S.`, thêm IN filter khách hàng `pr_detail_ids` (`S.PR_DETAIL_ID`), `item_ids` (`S.ITEM_ID`), `org_ids`, `wh_ids`, `job_ids`; search `s_desc`(LIKE %..%), `s_item_name`(JOIN I.ITEM_NAME), `s_tran_no`(LIKE ..%), `s_date`(`_apply_date_search`).
- **Hàng bán trả lại:** `IS_RETURN=1` ⇒ dòng trả lại (số âm/ghi đỏ). Cho lọc riêng nếu cần.
- **Endpoint:** `/api/sale`, `/api/sale/count`, `/api/sale/stream_csv`; CSV theo `SALE_CSV_COLS` (cặp `(col, "Nhãn VN")`). Reuse `_start_export_job`.
- **CẬP NHẬT 18/07/2026 — thêm 7 cột:** `PAYMENT_METHOD_ID`+`PAYMENT_METHOD_NAME` (map từ `DM_PAYMENT_METHOD`), `EXTRA_ID_2`+`EXTRA_NAME_2` (map từ `DM_EXTRA_2` — SALE_VIEW chỉ có ID, `EXTRA_ID_2` = "nguồn đơn" vd ShopeeFood), `INCOME_AMOUNT`, `VAT_INCOME_AMOUNT`, `COMMENTS`. Các cột trên SALE_VIEW gom vào `SALE_EXTRA_COLUMNS` và **chỉ SELECT nếu tồn tại** (guard `_sale_dim_info()` introspect INFORMATION_SCHEMA + cache theo DB — tránh crash pool khi tên cột sai). Tên HTTT/nguồn map ở Python. Chi tiết đồng bộ frontend (42 cột) xem `KIEN_TRUC_TOAN_TAP.md` mục 13.
- **Kiểm thử:** so tổng `TOTAL_AMOUNT`/`AMOUNT` với doanh thu (TK 511) BC001 KQKD cùng kỳ để chốt khớp; lưu ý `SALE_VIEW` là giá trị hóa đơn bán — đối chiếu mẫu trước khi tin tuyệt đối.

---
*Lập ngày 24/06/2026 từ bản LedgerReport đã validated. Mọi công thức đã đối chiếu DB IACC_CHULONG tháng 1–6/2026. Mục 8 (danh sách chứng từ) mô tả pattern Ledger/Purchase/Warehouse + recipe cho Danh sách chứng từ Bán hàng (SALE_VIEW).*
