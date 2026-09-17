import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILE_PATH = r"d:\IACC HCM\iPOS ACC\ACC PMKT\LedgerReport\index.html"
with open(FILE_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Fix buildGroupedData
buildGroupedData_find = """        function buildGroupedData(rawData, groupCols, sumFields) {
            if (!groupCols || groupCols.length === 0) return rawData;
            const rootGroups = new Map();
            for(let i=0; i<rawData.length; i++) {
                const row = rawData[i];
                let currentMap = rootGroups;
                for(let j=0; j<groupCols.length; j++) {
                    const col = groupCols[j];
                    const val = row[col] || '(Trống)';
                    
                    let key = val;
                    if(j > 0) key = Array.from(currentMap.keys()).join('|') + '|' + val; // unique key path"""

buildGroupedData_replace = """        function buildGroupedData(rawData, groupCols, sumFields) {
            if (!groupCols || groupCols.length === 0) return rawData;
            const rootGroups = new Map();
            for(let i=0; i<rawData.length; i++) {
                const row = rawData[i];
                let currentMap = rootGroups;
                let parentKey = '';
                for(let j=0; j<groupCols.length; j++) {
                    const col = groupCols[j];
                    const val = row[col] || '(Trống)';
                    
                    let key = parentKey ? parentKey + '|' + val : val;
                    parentKey = key; // Save for next level"""

html = html.replace(buildGroupedData_find, buildGroupedData_replace)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print("Fixed buildGroupedData!")
