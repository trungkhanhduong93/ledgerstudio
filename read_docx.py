import zipfile, xml.etree.ElementTree as ET
import sys
sys.stdout.reconfigure(encoding='utf-8')

def read_docx(path):
    z = zipfile.ZipFile(path)
    xml_content = z.read('word/document.xml')
    tree = ET.XML(xml_content)
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    text = []
    
    # Simple extraction of tables for better viewing
    for table in tree.iterfind('.//w:tbl', ns):
        text.append('\n[TABLE]')
        for row in table.iterfind('.//w:tr', ns):
            row_data = []
            for cell in row.iterfind('.//w:tc', ns):
                cell_text = ''.join([node.text for node in cell.iterfind('.//w:p/w:r/w:t', ns) if node.text])
                row_data.append(cell_text.strip())
            text.append(' | '.join(row_data))
        text.append('[/TABLE]\n')
        
    return '\n'.join(text)

print('--- BC007 S03a-DN ---')
print(read_docx(r'BaoCaoMau\S03a-DN-Pl3.docx'))
print('\n--- BC008 So Chi Tiet Tai Khoan ---')
print(read_docx(r'BaoCaoMau\So Chi Tiet Tai Khoan.docx'))
