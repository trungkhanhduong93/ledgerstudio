# Sửa Lỗi: Bộ Lọc Không Hoạt Động Trên Máy Khác

## Vấn đề
Khi build EXE và gửi qua máy khác, bộ lọc không hoạt động. Lý do chính: **ứng dụng phụ thuộc vào CDN (internet)** để tải:
- React (unpkg.com)
- Tailwind CSS (cdn.tailwindcss.com)
- Babel (unpkg.com)
- Google Fonts

Nếu máy khác **không có internet** hoặc **bị chặn truy cập CDN**, các thư viện không tải → React không khởi chạy → giao diện rỗng, bộ lọc không hoạt động.

## Cách Sửa

### 1. Cơ bản: Đảm bảo máy khác có Internet
- Kiểm tra kết nối internet trên máy khác
- Kiểm tra firewall/proxy không chặn truy cập đến:
  - `unpkg.com`
  - `cdn.tailwindcss.com`
  - `fonts.googleapis.com`

### 2. Nâng cao: Tạo bản Offline (không cần internet)

#### Option A: Dùng Tailwind CSS + React từ CDN nhưng có fallback
**Đã áp dụng** - Thêm warning khi CDN fail và fallback CSS cơ bản.

#### Option B: Bundle React + Tailwind vào HTML (khuyên dùng)
Tạo file `index-offline.html` với React + Tailwind inline:

```bash
# 1. Tải các thư viện
curl -s https://unpkg.com/react@18/umd/react.production.min.js > react.min.js
curl -s https://unpkg.com/react-dom@18/umd/react-dom.production.min.js > react-dom.min.js
curl -s https://unpkg.com/@babel/standalone/babel.min.js > babel.min.js
curl -s https://cdn.tailwindcss.com > tailwind.min.css

# 2. Build lại EXE
BuildEXE.bat
```

#### Option C: Chuyển sang Vue.js hoặc Alpine.js (nhẹ hơn, không cần CDN)
Alpine.js chỉ 15KB, có thể inline hoàn toàn.

### 3. Thay Đổi Đã Thực Hiện

#### server.py
```python
# Thêm route phục vụ static files
@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(resource_path("."), filename)
```

#### index.html
```html
<!-- Thêm offline detection -->
<div id="offline-warning" style="display:none;">
    ⚠️ Không thể kết nối CDN - Cần Internet để chạy
</div>

<script>
    setTimeout(() => {
        if (typeof React === 'undefined') {
            document.getElementById('offline-warning').style.display = 'block';
        }
    }, 5000);
</script>
```

#### BuildEXE.bat
```batch
# Thêm cleanup cache
rmdir /s /q build dist\*.spec 2>nul
```

## Kiểm Tra Kết Quả

```powershell
# 1. Build EXE
BuildEXE.bat

# 2. Test trên máy hiện tại (có internet)
dist\iPOS_Ledger_Studio.exe
# → Bộ lọc hoạt động ✓

# 3. Test trên máy không internet
# Tắt WiFi/LAN, chạy lại
# → Sẽ thấy warning CDN hoặc fallback UI
```

## Khuyến Nghị Lâu Dài

1. **Build offline version**: Download CDN files, inline vào HTML
2. **Dùng Web Framework nhẹ**: Alpine.js thay React (15KB vs 180KB)
3. **Ship bản hybrid**: 
   - Online mode (nhanh, dùng CDN)
   - Offline mode (dùng file local, nếu tắt CDN)

## Liên Hệ
Nếu máy khác vẫn lỗi:
- Kiểm tra Console (F12) xem có lỗi gì
- Screenshot báo lỗi
- Kiểm tra kết nối network trong Dev Tools
