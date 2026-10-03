# Giao việc cho Gemini: thêm cột "Thuế suất" vào 2 bảng Doanh thu chờ phân bổ

> Người giao: Trum · Soạn: Claude, 03/10/2026 · Dự án: **LedgerStudio** (`D:\IACC HCM\iPOS ACC\ACC PMKT\LedgerStudio`)
> File này chỉ nói phần liên quan tới việc này. Luật chung của dự án nằm ở `GEMINI.md` (đọc mục 1, Bẫy 2, 4, 5, 12, 14, 23 và mục 5).
> Repo `trungkhanhduong93/ledgerstudio` là **Public** → không ghi IP server, user, mật khẩu DB vào file này hay bất kỳ file nào sẽ commit.

## 1. Yêu cầu

Thêm cột **Thuế suất** vào 2 tab dữ liệu:

| Tab trên app | id tab | Endpoint |
|---|---|---|
| Danh sách doanh thu chờ phân bổ | `income_alloc` | `/api/income_alloc`, `/api/income_alloc/stream_csv` |
| Doanh thu chờ phân bổ theo tháng | `income_alloc_month` | `/api/income_alloc_month`, `/api/income_alloc_month/stream_csv` |

Cách lấy số:

```
INCOME_ALLOCATION.ITEM_ID ──► DM_ITEM.ITEM_ID ──► DM_ITEM.VAT_TAX_ID
                                                     │
DM_VAT_TAX.VAT_TAX_ID ◄──────────────────────────────┘ ──► DM_VAT_TAX.VAT_TAX_RATE
```

Hiển thị: số thuế suất + dấu `%` → `10%`, `8%`, `5%`, `0%`. Không tìm thấy (ITEM_ID trống, hàng không có mã thuế, mã thuế không có trong DM_VAT_TAX) → ô trống.

Kiểu cột (đã tra schema iPOS): `DM_ITEM.VAT_TAX_ID` nvarchar · `DM_VAT_TAX.VAT_TAX_ID` nvarchar · `DM_VAT_TAX.VAT_TAX_RATE` **money** (pyodbc trả `Decimal('10.0000')`, xem Bẫy 12).

## 2. Kiến trúc phần sẽ đụng

App = `server.py` (Flask + PyODBC, 1 file ~460 KB) + `index.html` (React + Babel, 1 file ~730 KB). EXE nhúng bản **dịch sẵn** `build_web/`, không nhúng `index.html` gốc (Bẫy 14).

### 2.1 Backend: `server.py`, khối "DOANH THU CHỜ PHÂN BỔ" (khoảng dòng 4540–5390)

Tìm theo tên hàm, số dòng chỉ để tham khảo.

**Tab danh sách (`income_alloc`)**

| Thứ | Vai trò |
|---|---|
| `_income_alloc_cols()` | Dò `INFORMATION_SCHEMA` 1 lần mỗi DB, chỉ SELECT cột thực có (CHULONG thiếu `RECEIVE_DATE`). Mẫu để bắt chước khi dò cột mới. |
| `_income_alloc_select_list()` | SELECT list chung cho trang, export_all và stream_csv. **Thêm cột thuế ở đây.** |
| `_income_alloc_sort_whitelist()` | Whitelist sắp xếp, dùng chung cho cả tab theo tháng (`_income_month_sort` gọi lại). |
| `INCOME_ALLOC_FROM` | Mệnh đề FROM dùng cho cả câu đếm + cộng tổng. **Không thêm JOIN vào đây.** |
| `INCOME_ALLOC_NUM_COLS` + `_income_alloc_enrich()` | Đổi Decimal → float trước khi trả JSON. |
| `INCOME_ALLOC_CSV_COLS` + `transform` trong `get_income_alloc_stream_csv()` | Cột + giá trị file xuất. Thứ tự phải khớp `INCOME_ALLOC_EXPORT_COLS` ở `index.html`. |

**Tab theo tháng (`income_alloc_month`)**

| Thứ | Vai trò |
|---|---|
| `_income_month_page_sql()` | Câu lấy trang. CTE `K` sắp xếp + đánh số trên cột hẹp, câu SELECT cuối mới nối lấy đủ cột **cho các dòng của trang**. **Thêm cột thuế vào SELECT cuối** (sau `FROM K JOIN dbo.INCOME_ALLOCATION A`), không thêm vào `K`. |
| `_income_month_select()` | SELECT list của bản xuất. **Thêm cột thuế ở đây.** |
| `INCOME_MONTH_FROM` | Dùng cho `K`, câu đếm, bản xuất. **Không thêm JOIN vào đây.** |
| `_income_month_row()` | Đổi Decimal → float, strip chuỗi. |
| `_income_month_export_cols()` | Cột file xuất, đúng thứ tự mẫu "Bao cao_DTCTH". |
| `_income_month_xlsx_spec()` | Công thức Excel (Lũy kế trong kỳ, Còn lại) + cột in đậm, tính vị trí theo **khoá cột** → chèn cột mới thì công thức tự dời. Vẫn phải mở file kiểm. |

### 2.2 Frontend: `index.html`

| Thứ | Dòng (tham khảo) | Vai trò |
|---|---|---|
| `fmtRate` | ~1408 | Có sẵn: `r => r.VAT_TAX_RATE != null && r.VAT_TAX_RATE !== '' ? r.VAT_TAX_RATE + '%' : ''`. **Dùng lại, đừng viết hàm mới.** |
| `INCOME_ALLOC_GRID.cols` | ~1529 | Khai báo cột tab danh sách (Bẫy 23: thêm cột = thêm 1 phần tử). |
| `INCOME_MONTH_GRID.cols` | ~1577 | Khai báo cột tab theo tháng. |
| `INCOME_ALLOC_EXPORT_COLS` | ~6551 | Khoá + nhãn file xuất tab danh sách. |
| `INCOME_MONTH_EXPORT_COLS` | ~6587 | Tự sinh từ `INCOME_MONTH_GRID` → không cần sửa. |
| `readColLayout` | ~1124 | Người dùng đã lưu bố cục cột → cột mới tự chèn sau cột đứng trước nó. Không cần sửa. |

## 3. Lưu ý: đọc trước khi gõ code

1. Chỉ sửa LedgerStudio. `LedgerReport` nằm cùng thư mục cha, kiến trúc giống hệt, **cấm sửa**.
2. Sửa đúng chỗ, không viết lại file. `server.py` và `index.html` rất lớn. Rewrite là mất code người khác.
3. Không thêm JOIN vào `INCOME_ALLOC_FROM` / `INCOME_MONTH_FROM`. Hai hằng này dùng cho câu đếm và cộng tổng. Nếu `DM_ITEM` có 2 dòng cùng `ITEM_ID`, JOIN sẽ nhân dòng → tổng Doanh thu, Lũy kế, Còn lại sai mà không báo lỗi. Dùng **subquery vô hướng** trong SELECT list (mục 4.1): không đổi số dòng, không đụng câu đếm.
4. Không lấy từ danh mục nạp sẵn (`_meta_cache['items']`). Danh mục đó chỉ có mục ACTIVE=1. Trum 29/09 đã chuyển tên đối tượng sang JOIN thẳng `DM_PR_DETAIL` vì lý do này. Hàng ngừng dùng vẫn phải có thuế suất.
5. Dò cột trước khi SELECT (Bẫy 5). SELECT cột không tồn tại → API trả 500 + ngắt connection pool, tab chết hẳn. DB khách mỗi nơi một cấu trúc. Bắt chước `_sale_link_ok()`: dò `INFORMATION_SCHEMA` 1 lần mỗi DB, cache theo tên DB, thiếu cột thì trả `CAST(NULL AS MONEY)`.
6. SQL phải chạy được trên SQL Server 2008. Không `CONCAT`, `FORMAT`, `IIF`. Ghép dấu `%` ở Python / JS, không ghép trong SQL.
7. Không thêm dấu `?` mới. Subquery dùng tham chiếu cột `A.ITEM_ID`, không tham số. Thêm `?` là lệch thứ tự params (Bẫy 2) → 0 dòng.
8. `WITH (NOLOCK)` gõ tay, đúng cú pháp `dbo.DM_ITEM IT WITH (NOLOCK)`. Đừng chạy script tự chèn hint (Bẫy 4 từng làm hỏng alias).
9. Chuỗi tiếng Việt gõ ký tự thật (`Thuế suất`), không dùng `\u` escape khi vá file.
10. Xuất Excel ghi chữ `10%`, không ghi số 10. Trum yêu cầu hiện kèm `%`. Ghi Decimal thì `_write_xlsx_to_disk` định dạng `#,##0` → ô hiện `10`, mất dấu `%`. Thuế suất không ai cộng, để dạng chữ không mất gì.
11. Sửa `index.html` xong phải build lại EXE mới thấy trên bản EXE (Bẫy 14). `python server.py` chạy bản CDN + Babel, không chứng minh được bản EXE.

## 4. Các bước làm

### Bước 0: Kiểm dữ liệu thật (chỉ SELECT, không sửa DB)

Xin Trum thông tin đăng nhập DB test. **Không ghi lại vào file nào.** Chạy:

```sql
-- a) ITEM_ID có trùng không (trùng → MAX lấy 1 giá trị, phải báo Trum)
SELECT ITEM_ID, COUNT(*) FROM dbo.DM_ITEM GROUP BY ITEM_ID HAVING COUNT(*) > 1;
-- b) VAT_TAX_ID có trùng không
SELECT VAT_TAX_ID, COUNT(*) FROM dbo.DM_VAT_TAX GROUP BY VAT_TAX_ID HAVING COUNT(*) > 1;
-- c) Toàn bộ bảng thuế suất
SELECT VAT_TAX_ID, VAT_TAX_NAME, VAT_TAX_RATE, ACTIVE FROM dbo.DM_VAT_TAX;
```

**Dừng lại hỏi Trum** nếu: (a) hoặc (b) ra dòng; hoặc (c) có thuế suất âm (kiểu "KCT" = -1) hay nhiều mã cùng 0% nhưng tên khác nhau ("0%", "KCT", "KKKNT"). Lúc đó cần chốt có hiện tên thay cho số không. Không tự đoán.

### Bước 1: `server.py`: helper dùng chung

Đặt ngay dưới `_income_alloc_sort_whitelist()`:

```python
_vat_rate_cache = {}

def _vat_rate_ok():
    """DM_ITEM.VAT_TAX_ID + DM_VAT_TAX (VAT_TAX_ID, VAT_TAX_RATE) có đủ không — dò 1 lần mỗi CSDL (Bẫy 5)."""
    db = (session.get('db_config') or {}).get('database', '')
    if db not in _vat_rate_cache:
        try:
            cur = get_connection().cursor()
            cur.execute("SELECT UPPER(TABLE_NAME), UPPER(COLUMN_NAME) FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME IN ('DM_ITEM', 'DM_VAT_TAX')")
            have = {(t, c) for t, c in cur.fetchall()}
            _vat_rate_cache[db] = {('DM_ITEM', 'ITEM_ID'), ('DM_ITEM', 'VAT_TAX_ID'),
                                   ('DM_VAT_TAX', 'VAT_TAX_ID'), ('DM_VAT_TAX', 'VAT_TAX_RATE')} <= have
        except Exception:
            _vat_rate_cache[db] = False
    return _vat_rate_cache[db]

def _vat_rate_sql(alias="A"):
    """Thuế suất của hàng trên dòng phân bổ: ITEM_ID → DM_ITEM.VAT_TAX_ID → DM_VAT_TAX.VAT_TAX_RATE.
    Subquery vô hướng (không JOIN vào FROM) → không đổi số dòng, câu đếm / cộng tổng giữ nguyên."""
    if not _vat_rate_ok():
        return "CAST(NULL AS MONEY)"
    return (f"(SELECT MAX(VT.VAT_TAX_RATE) FROM dbo.DM_ITEM IT WITH (NOLOCK) "
            f"JOIN dbo.DM_VAT_TAX VT WITH (NOLOCK) ON VT.VAT_TAX_ID = IT.VAT_TAX_ID "
            f"WHERE IT.ITEM_ID = {alias}.ITEM_ID)")

def _fmt_rate(v):
    """Decimal('10.0000') → '10%' cho file xuất; None → None (ô trống)."""
    return None if v is None else f"{float(v):g}%"
```

### Bước 2: `server.py`: tab danh sách

1. `_income_alloc_select_list()`: thêm `{_vat_rate_sql('A')} AS VAT_TAX_RATE` vào cuối SELECT list (hàm đang trả chuỗi thường, đổi phần đuôi sang f-string hoặc nối chuỗi).
2. `_income_alloc_sort_whitelist()`: thêm `"VAT_TAX_RATE": _vat_rate_sql("A")` vào `wl.update({...})`. Tab theo tháng tự hưởng vì `_income_month_sort` gọi lại hàm này.
3. `INCOME_ALLOC_NUM_COLS`: thêm `"VAT_TAX_RATE"` → `_income_alloc_enrich` đổi Decimal → float (JSON ra `10.0`, `fmtRate` hiện `10%`).
4. `INCOME_ALLOC_CSV_COLS`: chèn `("VAT_TAX_RATE","Thuế suất")` ngay sau `("ITEM_NAME","Tên hàng hóa")`.
5. `transform` trong `get_income_alloc_stream_csv()`: thêm `d['VAT_TAX_RATE'] = _fmt_rate(d.get('VAT_TAX_RATE'))` trước dòng `return`.

### Bước 3: `server.py`: tab theo tháng

1. `_income_month_page_sql()`: trong câu SELECT cuối (dòng có `PD.PR_DETAIL_NAME AS PR_DETAIL_NAME, AC.ACCOUNT_NAME AS ACCOUNT_NAME_DES{out_tot}`), thêm `, {_vat_rate_sql('A')} AS VAT_TAX_RATE` trước `{out_tot}`. **Không thêm vào `K`.**
2. `_income_month_select()`: thêm `f"{_vat_rate_sql('A')} AS VAT_TAX_RATE"` vào list `nums` (bản xuất dùng).
3. `_income_month_row()`: thêm `"VAT_TAX_RATE"` vào list cột số đổi float.
4. `_income_month_export_cols()`: chèn `("VAT_TAX_RATE", "Thuế suất")` ngay sau `("ITEM_ID", "Hàng hóa")`.
5. `transform` trong `get_income_alloc_month_stream_csv()`: đổi riêng khoá `VAT_TAX_RATE` qua `_fmt_rate`, các khoá khác giữ nguyên như hiện tại.
6. **Không** thêm `VAT_TAX_RATE` vào `sum_cols` / `bold_cols` của `_income_month_xlsx_spec`.

### Bước 4: `index.html`

1. `INCOME_ALLOC_GRID.cols`: chèn ngay sau phần tử `ITEM_NAME`:
   ```js
   { id: 'VAT_TAX_RATE',           label: 'Thuế suất',     sort: 'VAT_TAX_RATE',      th: 'border-r w-16',          search: 1, td: 'border-r text-center', v: fmtRate },
   ```
2. `INCOME_MONTH_GRID.cols`: chèn ngay sau phần tử `ITEM_ID`, cùng khai báo như trên.
3. `INCOME_ALLOC_EXPORT_COLS`: chèn `['VAT_TAX_RATE','Thuế suất']` ngay sau `['ITEM_NAME','Tên hàng hóa']` (cùng vị trí với server).
4. Không khai `q:` và không đặt `search: 2`: lọc theo cột chỉ chạy trên các dòng đã tải. Gõ `10` khớp `10%`.

### Bước 5: Kiểm cú pháp

```bash
python -c "import ast; ast.parse(open('server.py', encoding='utf-8').read()); print('PYTHON_SYNTAX_OK')"
```

JSX kiểm bằng `node check_babel.js` (parse khối `<script type="text/babel">` của `index.html`). Build EXE ở mục 6 cũng dịch lại JSX, lỗi là dừng.

## 5. Nghiệm thu: phải qua hết mới báo "xong"

Test backend bằng Flask `test_client` in-process (Bẫy 1), không qua cổng 5050.

| # | Kiểm gì | Đạt khi |
|---|---|---|
| 1 | Số liệu đúng | Lấy 3 dòng bất kỳ mỗi tab, tự chạy SQL tra `ITEM_ID → VAT_TAX_ID → VAT_TAX_RATE`. Khớp màn hình. |
| 2 | Không đổi tổng | Cùng bộ lọc, ghi `pagination.total_rows` + `summary` **trước và sau** khi sửa. Hai lần phải bằng nhau từng số. |
| 3 | Ô trống | Dòng có `ITEM_ID` trống hoặc hàng không có mã thuế → ô trống, không lỗi. |
| 4 | DB thiếu cột | Tạm cho `_vat_rate_ok()` trả `False` → cả 2 tab vẫn chạy, cột thuế trống. Test xong trả lại. |
| 5 | Sắp xếp | Bấm sắp theo Thuế suất ở cả 2 tab, tăng và giảm. Không lỗi 500, sang trang không lặp dòng. |
| 6 | Xuất Excel "Đầy đủ" | Cả 2 tab: cột "Thuế suất" đứng đúng vị trí, ô ghi `10%`. File theo tháng: mở ô Lũy kế trong kỳ và Còn lại, công thức vẫn trỏ đúng cột tháng / Doanh thu. Dòng tổng không cộng cột thuế. |
| 7 | Xuất Excel "Như đang xem" | Ẩn cột Thuế suất → file không có cột này. Hiện lại → có. |
| 8 | Bố cục đã lưu | Máy có `localStorage['ds_cols_income_alloc']` cũ → cột mới hiện sau Tên hàng hóa, không mất cột khác. |
| 9 | Tốc độ | Tab theo tháng lọc 3 tháng: so thời gian `page` trên thanh trạng thái (header `Server-Timing`) trước và sau. Tăng quá 20% thì báo Trum kèm số đo. |
| 10 | Bản EXE | Build xong mở EXE, kiểm lại #1 và #6. |

## 6. Build và bàn giao

1. Đóng app đang chạy: `taskkill /F /IM iPOS_Ledger_Studio.exe /T`.
2. Build: `python build_exe.py` (tự tăng `version.txt`). Đừng chạy `BuildEXE-LedgerStudio.bat` từ agent: có `pause`, sẽ treo.
3. `build_exe.py` in `[SUCCESS]` kể cả khi hỏng. **Tự so mtime** của `dist/iPOS_Ledger_Studio.exe` với giờ hiện tại, dung lượng quanh 15–16 MB.
4. Ghi 1 dòng changelog vào đầu `GEMINI.md` (dòng "Cập nhật gần nhất") và mục 13 của `KIEN_TRUC_TOAN_TAP.md`.
5. **Không commit, không push, không tạo Release** khi Trum chưa bảo. Khi được bảo: `git remote get-url origin` phải ra `.../ledgerstudio.git`.
6. Báo Trum theo khuôn `GEMINI.md` mục 1.2 ý 7. Mục nào ở bảng nghiệm thu chưa chạy thì ghi rõ "chưa chạy", không ghi "đạt".
