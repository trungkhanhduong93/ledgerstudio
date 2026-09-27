import os
import sys
import shutil
import subprocess

# ---------------------------------------------------------------------------
# TÊN EXE — ưu tiên tham số dòng lệnh, KHÔNG đoán theo thư mục.
#
# ⚠️ Bản cũ chỉ đoán bằng `'ledgerreport' in os.getcwd()`. Chạy sai thư mục là ra
# sai tên EXE mà không có gì cảnh báo — LedgerStudio build ra iPOS_Accounting_Report
# hoặc ngược lại. Nay mỗi project có file .bat riêng, tên khác hẳn nhau, và .bat
# truyền thẳng tên EXE vào đây:
#     BuildEXE-LedgerReport.bat  -> python build_exe.py iPOS_Accounting_Report
#     BuildEXE-LedgerStudio.bat  -> python build_exe.py iPOS_Ledger_Studio
# Không truyền gì thì vẫn đoán như cũ nhưng IN CẢNH BÁO to.
# ---------------------------------------------------------------------------
VALID_APP_NAMES = ('iPOS_Accounting_Report', 'iPOS_Ledger_Studio')

if len(sys.argv) > 1 and sys.argv[1].strip():
    APP_NAME = sys.argv[1].strip()
    if APP_NAME not in VALID_APP_NAMES:
        print(f"[LOI] Ten EXE '{APP_NAME}' khong hop le. Chi chap nhan: {', '.join(VALID_APP_NAMES)}")
        sys.exit(1)
else:
    APP_NAME = 'iPOS_Accounting_Report' if 'ledgerreport' in os.getcwd().lower() else 'iPOS_Ledger_Studio'
    print("=" * 70)
    print(f"[CANH BAO] Khong truyen ten EXE — dang DOAN theo thu muc: {APP_NAME}")
    print(f"           Thu muc hien tai: {os.getcwd()}")
    print(f"           Nen chay qua BuildEXE-LedgerReport.bat / BuildEXE-LedgerStudio.bat")
    print("=" * 70)

# ---------------------------------------------------------------------------
# BẢN WEB DỊCH SẴN (từ 27/09/2026) — EXE KHÔNG còn nhúng index.html gốc.
# webbuild/build.js dịch JSX sẵn (thay Babel chạy trong trình duyệt — đo máy dev: vẽ màn đăng nhập 7,6 s → 0,2 s),
# build Tailwind ra CSS tĩnh, đóng React/xlsx/font vào build_web/ → mở app không cần internet.
# Chạy TRƯỚC khi tăng version: build web lỗi thì dừng, không đốt số phiên bản.
# `python server.py` vẫn dùng index.html gốc (CDN + Babel) như cũ.
# ---------------------------------------------------------------------------
WEB_DIR = 'build_web'

def build_web():
    node = shutil.which('node')
    npm = shutil.which('npm')
    if not node or not npm:
        print('[LOI] Khong tim thay Node.js (node/npm) trong PATH — can de dich san giao dien. Cai Node 18+ roi build lai.')
        sys.exit(1)
    if not os.path.isdir(os.path.join('webbuild', 'node_modules')):
        print('Cai cong cu build web (lan dau): npm ci trong webbuild/ ...')
        if subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd='webbuild').returncode != 0:
            print('[LOI] npm ci that bai. Kiem tra ket noi mang.')
            sys.exit(1)
    if subprocess.run([node, os.path.join('webbuild', 'build.js')]).returncode != 0:
        print('[LOI] Dich san giao dien that bai — xem thong bao [LOI webbuild] o tren.')
        sys.exit(1)

build_web()

ICON_NAME = 'icon.ico'
ADD_DATA = [
    f'{WEB_DIR}/index.html;.',
    f'{WEB_DIR}/app.js;.',
    f'{WEB_DIR}/app.css;.',
    f'{WEB_DIR}/vendor;vendor',
    'install_driver.ps1;.'
]
if os.path.exists('manifest.json'):
    ADD_DATA.append('manifest.json;.')
if os.path.exists('icon.svg'):
    ADD_DATA.append('icon.svg;.')
if os.path.exists(f'{WEB_DIR}/assets'):
    ADD_DATA.append(f'{WEB_DIR}/assets;assets')   # ảnh giao diện (sóc màn đăng nhập) — webbuild chép từ assets/

VERSION_FILE = 'version.txt'
# version.txt phải nhúng vào EXE: server.py đọc file này rồi tiêm vào APP_VERSION của index.html
# (thêm SAU khi ghi version mới ở dưới, để bundle chứa đúng version vừa tăng).

def get_next_version(v_str):
    try:
        parts = list(map(int, v_str.strip().split('.')))
        if len(parts) != 3:
            parts = [1, 2, 0]
    except:
        parts = [1, 2, 0]
        
    major, minor, patch = parts
    
    if patch < 9:
        patch += 1
    else:
        patch = 0
        minor += 1
        
    return f'{major}.{minor}.{patch}'

# Read current version
if os.path.exists(VERSION_FILE):
    with open(VERSION_FILE, 'r') as f:
        current_version = f.read().strip()
else:
    current_version = '1.1.9' # So it becomes 1.2.0 on first run
    with open(VERSION_FILE, 'w') as f:
        f.write(current_version)

new_version = get_next_version(current_version)

print(f'\n====================================')
print(f' Building {APP_NAME} v{new_version} ')
print(f'====================================\n')

# Save new version
with open(VERSION_FILE, 'w') as f:
    f.write(new_version)

ADD_DATA.append(f'{VERSION_FILE};.')

# Generate version_info.txt
# Tên hiển thị (Task Manager, Properties của file EXE) — Studio đổi thành DataStudio từ 27/09/2026.
# Tên FILE vẫn là iPOS_Ledger_Studio.exe: updater chỉ nhận đúng tên asset đó (CLAUDE.md Bẫy 13).
DISPLAY_NAME = 'DataStudio' if APP_NAME == 'iPOS_Ledger_Studio' else APP_NAME
v_parts = list(map(int, new_version.split('.')))
v_tuple = f'{v_parts[0]}, {v_parts[1]}, {v_parts[2]}, 0'

version_info = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v_tuple}),
    prodvers=({v_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'iPOS.vn'),
        StringStruct('FileDescription', '{DISPLAY_NAME}'),
        StringStruct('FileVersion', '{new_version}'),
        StringStruct('InternalName', '{APP_NAME}'),
        StringStruct('OriginalFilename', '{APP_NAME}.exe'),
        StringStruct('ProductName', '{DISPLAY_NAME}'),
        StringStruct('ProductVersion', '{new_version}')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)"""

with open('version_info.txt', 'w') as f:
    f.write(version_info)

# Build command
cmd = [
    sys.executable, '-m', 'PyInstaller',
    '--noconsole', '--onefile', '--clean', '--noconfirm',
    '--name', APP_NAME,
    '--icon', ICON_NAME,
    '--version-file', 'version_info.txt',
    '--collect-submodules', 'pyodbc',
    '--hidden-import', 'xlsx_report',
    # Máy build có cài IPython/numpy/matplotlib (không liên quan app). PyInstaller lần theo import tuỳ chọn
    # flask.cli → python-dotenv → dotenv.ipython → IPython → numpy/matplotlib… ⇒ EXE phình 15,8 MB → 43 MB
    # (bản 1.8.1, 16/09/2026), mở app phải giải nén lâu hơn. App không dùng tới các gói này.
    '--exclude-module', 'IPython', '--exclude-module', 'matplotlib', '--exclude-module', 'matplotlib_inline',
    '--exclude-module', 'numpy', '--exclude-module', 'pandas', '--exclude-module', 'PIL',
]
for data in ADD_DATA:
    cmd.extend(['--add-data', data])
cmd.append('server.py')

print('Running PyInstaller...')
subprocess.run(cmd)
print(f'\n[SUCCESS] Built {APP_NAME}.exe v{new_version} in dist folder.')
