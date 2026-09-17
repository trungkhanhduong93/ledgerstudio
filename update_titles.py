import sys
with open('index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if "{reportType === 'BC006' ? 'BẢNG CÂN ĐỐI PHÁT SINH' : 'BẢNG CÂN ĐỐI KẾ TOÁN'}" in l:
        lines[i] = l.replace("{reportType === 'BC006' ? 'BẢNG CÂN ĐỐI PHÁT SINH' : 'BẢNG CÂN ĐỐI KẾ TOÁN'}", "{reportType === 'BC006' ? 'BẢNG CÂN ĐỐI PHÁT SINH' : reportType === 'BC007' ? 'SỔ NHẬT KÝ CHUNG' : reportType === 'BC008' ? 'SỔ CHI TIẾT TÀI KHOẢN' : 'BẢNG CÂN ĐỐI KẾ TOÁN'}")
    
    if "{reportType === 'BC005' ? 'Mẫu B01 - DN' : 'Mẫu B02 - DN'}" in l:
        lines[i] = l.replace("{reportType === 'BC005' ? 'Mẫu B01 - DN' : 'Mẫu B02 - DN'}", "{reportType === 'BC005' ? 'Mẫu B01 - DN' : reportType === 'BC006' ? 'Mẫu B02 - DN' : reportType === 'BC007' ? 'Mẫu S03a-DN' : 'Mẫu S38-DN'}")

with open('index.html', 'w', encoding='utf-8') as f:
    f.writelines(lines)
