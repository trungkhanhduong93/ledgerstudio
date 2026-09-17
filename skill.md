# 🚀 Cẩm Nang Toàn Tập: iPOS Accounting Ledger Report

Tài liệu này là hướng dẫn tổng hợp (Master Guide) cho dự án **Ledger Report**, bao quát từ kiến trúc, cách đóng gói, quy trình thêm mới báo cáo cho đến các tiêu chuẩn giao diện và kinh nghiệm sửa lỗi.

---

## 1. 🏗️ Tổng Quan Kiến Trúc (Architecture)

Dự án áp dụng mô hình **Single-Page Application (SPA)** kết hợp **Python Backend** nhẹ, tối ưu cho việc truy xuất dữ liệu lớn từ hệ thống iPOS ACC.

*   **Backend (`server.py`)**: Viết bằng Python (Flask + PyODBC).
    *   Quản lý kết nối SQL Server (iPOS ACC) bằng Connection Pool.
    *   Áp dụng `global_db_lock` để đồng bộ luồng, tránh treo database.
    *   Tích hợp nén `gzip` tự động cho JSON payload để tối ưu băng thông khi tải hàng trăm ngàn dòng.
    *   Tự động phát hiện lỗi mất kết nối SQL (HY000, 08S01) và thực hiện reconnect (chuẩn Vibe-Guard).
*   **Frontend (`index.html`)**: Chạy trực tiếp ReactJS (thông qua Babel standalone) và TailwindCSS qua CDN.
    *   Không cần Node.js server. Một file `index.html` gánh toàn bộ UI.
    *   Sử dụng kỹ thuật **Virtual Scroll** (windowing) và `useMemo` để render các bảng dữ liệu khổng lồ mà không bị Crash RAM.
*   **Triển khai/Đóng gói**: 
    *   Chạy server nội bộ qua `RunReport.bat` (Python Waitress/Flask).
    *   Sử dụng PyInstaller (`BuildEXE.bat`) để gói gọn mọi thứ thành 1 file `.exe` duy nhất.

---

## 2. 🛠️ Hướng Dẫn Build & Đóng Gói (Build EXE)

Để mang sang máy khác chạy độc lập (Standalone), hãy đóng gói dự án thành 1 file duy nhất.

1.  **Yêu cầu môi trường**: Máy tính cần cài đặt **Python 3.9+** (Nhớ tick *Add Python to PATH* khi cài đặt).
2.  **Khởi chạy kịch bản Build**: Chạy file `BuildEXE.bat`
    *   Script sẽ tự động cài các thư viện yêu cầu: `flask`, `flask-cors`, `pyodbc`, `pillow`, `xlsxwriter`.
    *   Dọn dẹp các bản build cũ.
    *   Dùng **PyInstaller** để đóng gói `server.py` (chế độ ẩn console `--noconsole`), đồng thời nhúng kèm `index.html`, `install_driver.ps1`, `manifest.json`.
3.  **Kết quả**: Tệp tin `iPOS_Accounting_Report.exe` sẽ được tạo ra trong thư mục `dist/`.
4.  **Lưu ý khi chạy trên máy đích**: Máy đích cần cài đặt `ODBC Driver 17 for SQL Server`. Ứng dụng có cơ chế tự gợi ý cài đặt (`install_driver.ps1`).

---

## 3. ✨ Tiêu Chuẩn Giao Diện & Hiệu Năng (@ui-premium-kit)

Hệ thống bắt buộc tuân thủ chuẩn giao diện **Premium & Professional**:

*   **Aesthetics**: Áp dụng triết lý Glassmorphism (`backdrop-blur-md`, `bg-white/80`), đổ bóng mềm (`shadow-sm`, `shadow-xl`). Góc bo tròn `rounded-xl` đến `rounded-3xl`.
*   **Hiển Thị Bảng (Table)**: 
    *   Luôn giữ Header cố định (`<thead className="sticky top-0 ...">`). Header sortable bằng component `<SortableHeader>`.
    *   Với bảng dự kiến > 1000 dòng, **BẮT BUỘC** dùng Virtual Scroll.
    *   Thanh cuộn thiết kế mỏng, thanh lịch (custom scrollbar).
*   **Bộ Lọc (Filters)**:
    *   Đặt gọn trong khung điều khiển trên cùng (Filter bar).
    *   Các bộ lọc `Select` dài (>10 items) phải có ô Search bên trong (Filter Dropdown).
    *   Dropdown phải có `zIndex` đủ lớn để không bị che bởi Modal.
    *   Date Picker/Time Picker dùng custom UI, không dùng input thô mặc định của trình duyệt.
*   **Trạng thái Loading/Empty**: 
    *   Sử dụng Skeleton Pulse hoặc Spinner tinh tế, không dùng hàm `alert()`.
    *   Có icon Empty Box kèm text hướng dẫn nếu bộ lọc không trả về dữ liệu.

---

## 4. 🚀 Quy Trình Thêm Báo Cáo Mới (Add New Report)

Quy trình 4 bước chuẩn mực để mở rộng hệ thống với một báo cáo hoàn toàn mới (VD: `profit_loss` - Báo cáo KQKD).

### Bước 1: Khai Báo API Backend (`server.py`)
Tạo Route mới lấy dữ liệu SQL. Lưu ý xử lý an toàn kiểu dữ liệu (Date, None).

```python
@app.route("/api/profit_loss")
@with_db_lock
def get_profit_loss():
    # 1. Nhận params (from_date, to_date, etc.)
    # 2. Build SQL Query an toàn (tránh inject)
    sql = "EXEC usp_GetProfitLoss @FromDate=?, @ToDate=?"
    # 3. Trả về JSON: return jsonify({"data": rows, "total": len(rows)})
```

### Bước 2: Thiết Lập State & API Call Frontend (`index.html`)
Khai báo mảng chứa dữ liệu và hàm fetch data tương ứng.

```javascript
// 1. Thêm tab mới vào state
const [activeTab, setActiveTab] = useState('profit_loss'); 

// 2. State lưu data
const [profitLossData, setProfitLossData] = useState([]);

// 3. Hàm fetch data chuẩn
const loadProfitLoss = async () => {
    setLoading(true);
    try {
        const res = await fetch(`/api/profit_loss?from_date=${filters.from_date}...`);
        const json = await res.json();
        setProfitLossData(json.data || []);
    } catch (err) {
        console.error(err);
    } finally {
        setLoading(false);
    }
};
```

### Bước 3: Định Nghĩa Table Cột & Virtual Scroll (`index.html`)
Xác định danh sách các cột cần export Excel (sẽ map 1-1 với render Table). Thiết kế Table.

```javascript
// 1. Array phục vụ xuất Excel
const PROFIT_LOSS_EXPORT_COLS = [
    ['ACCOUNT_ID', 'Tài khoản'],
    ['DESCRIPTION', 'Diễn giải'],
    ['AMOUNT', 'Giá trị']
];

// 2. Render UI Bảng
{activeTab === 'profit_loss' && (
    <div className="flex-1 overflow-auto" ref={scrollRef}>
        <table className="w-max border-collapse min-w-full">
            <thead className="sticky top-0 bg-slate-50/95 backdrop-blur-md z-30 shadow-sm">
                <tr>
                    <SortableHeader field="ACCOUNT_ID" ...>Tài khoản</SortableHeader>
                    {/* Map tiếp các cột tương tự */}
                </tr>
            </thead>
            <tbody>
                {virtualRows.map(row => (
                   <tr key={row.ID} className="border-b hover:bg-slate-50">
                       <td>{row.ACCOUNT_ID}</td>
                   </tr>
                ))}
            </tbody>
        </table>
    </div>
)}
```

### Bước 4: Tích hợp Export Excel
Bổ sung nhánh logic vào hàm `exportExcel()` để trỏ đúng cấu hình Cột.

```javascript
// Tìm hàm exportExcel() trong index.html và map logic mới
const cols = kind === 'ledger' ? LEDGER_EXPORT_COLS 
           : kind === 'purchase' ? PURCHASE_EXPORT_COLS 
           : kind === 'warehouse' ? WAREHOUSE_EXPORT_COLS
           : PROFIT_LOSS_EXPORT_COLS; // Thêm ở đây

const prefix = kind === 'ledger' ? 'ChungTuTongHop_' 
             : kind === 'profit_loss' ? 'KetQuaKinhDoanh_' : '...';
```

---

## 5. 🛡️ Quy Tắc Tránh Lỗi Điển Hình (@vibe-guard)

Khi chỉnh sửa logic, cần đưa qua bộ Sanity Check sau để chống "Gãy" app:

*   **Crash do Date Parsing JS**: Trình duyệt có thể không hiểu chuỗi ngày SQL dạng `YYYY-MM-DD HH:mm:ss`. **Luôn luôn** tiền xử lý chuỗi: `new Date(dateString.replace(' ', 'T'))`.
*   **Crash JSX do thiếu Escape Code**: Dữ liệu lấy từ Database có thể chứa ký tự HTML (`<`, `>`). Tuyệt đối không dùng `dangerouslySetInnerHTML` để render text description trừ khi thực sự cần thiết và đã sanitize. Render an toàn: `<td>{row.DESCRIPTION}</td>`. Hoặc an toàn hơn `>{row.TEXT}<`.
*   **Treo RAM do Virtual Scroll**: Khi tính chiều cao bảng `virtualScroll`, nếu chiều cao dòng (`rowHeight`) fix cứng mà CSS lại làm nội dung tràn ra, kéo thanh cuộn sẽ bị giật và crash. Đảm bảo `<td className="truncate">` hoặc chiều cao cố định vững.
*   **Tràn Memory (Memory Leak)**: Các `useEffect` gắn Event Listeners (như `window.addEventListener('resize')` hay custom click outside) bắt buộc phải có lệnh `return () => window.removeEventListener(...)` để dọn dẹp.
*   **Lỗi Rò Rỉ Scope Component (Missing Props)**: Khi tách UI thành nhiều component, mọi state khai báo ở component cha bắt buộc phải được truyền xuống component con thông qua `props`. Việc "gọi đại" tên biến state của cha bên trong JSX của con sẽ làm vỡ Babel app ngay lập tức với lỗi `ReferenceError`.
*   **Lỗi Thiếu Cột Trong SQL View**: Các bảng View tổng hợp CÓ THỂ KHÔNG CHỨA cột chi tiết. Việc `SELECT` trực tiếp cột này sẽ làm API crash và khiến DB Pool ngắt kết nối. Luôn dùng `try-catch` thăm dò schema trước khi sử dụng động các cột phân tích phụ trợ.

---

## 6. 🔍 Xử Lý Lỗi / Khắc Phục Sự Cố (@debug-assist)

Nếu chuyển thư mục sang máy khác hoặc gặp lỗi không rõ nguyên nhân, hãy kiểm tra danh sách này:

### A. Lỗi Màn Hình Trắng / Bộ Lọc Không Chạy (Offline Error)
*   **Dấu hiệu**: Bật `.exe` lên nhưng giao diện trống trơn, hoặc ấn filter không ăn.
*   **Nguyên nhân**: Frontend (`index.html`) sử dụng CDN để lấy React và TailwindCSS (`unpkg.com`, `cdn.tailwindcss.com`). Máy tính đích **không có kết nối internet** hoặc tường lửa (Firewall) chặn.
*   **Cách Debug**: Bật trình duyệt, nhấn `F12` (Developer Tools) -> Tab **Network** để xem các file `.js`, `.css` nào báo lỗi màu đỏ (Failed).
*   **Cách Fix Mạng**: Kết nối Internet cho máy, hoặc tải file `.js`, `.css` về nhúng trực tiếp vào ổ cứng cục bộ (Inline bundle).

### B. Lỗi Không Kết Nối Được Database SQL
*   **Dấu hiệu**: Báo lỗi `Communication link failure`, `HY000`, `08S01`.
*   **Nguyên nhân**: Mạng chập chờn làm chết session SQL, hoặc Connection Pool đang giữ kết nối rác.
*   **Xử lý trong Code**: Backend tự Invalid Pool khi gặp mã lỗi mạng và tự động Re-connect nhờ decorator `@with_db_lock`. Người dùng chỉ việc reload lại hoặc bấm tìm kiếm lần nữa.

### C. Lỗi Port Đã Bị Chiếm Đóng (Port 5050 In Use)
*   **Dấu hiệu**: Chạy app báo lỗi `Address already in use`.
*   **Nguyên nhân**: Một process cũ chưa tắt hẳn, vẫn đang ngậm Port 5050.
*   **Xử lý trong Code**: Hàm `kill_process_on_port(5050)` ở đầu `server.py` tự động `taskkill` tiến trình đang chiếm dụng port trước khi khởi động.
