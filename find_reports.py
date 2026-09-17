import sys, re
sys.stdout.reconfigure(encoding='utf-8')
with open('index.html', 'r', encoding='utf-8') as f:
    t = f.read()

needle = "reportType === 'BC007'"
pos = t.find(needle)
while pos >= 0:
    line = t[:pos].count('\n') + 1
    ctx = t[max(0,pos-20):min(len(t),pos+200)]
    print(f"Line {line}:")
    print(ctx[:220])
    print('='*60)
    pos = t.find(needle, pos+1)
