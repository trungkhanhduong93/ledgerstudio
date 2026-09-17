import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

m = re.search(r'<script type="text/babel">(.*?)</script>', html, re.DOTALL)
if m:
    jsx = m.group(1)
    print("JSX length:", len(jsx))
    open_b = jsx.count('{')
    close_b = jsx.count('}')
    open_p = jsx.count('(')
    close_p = jsx.count(')')
    print(f"Braces: {open_b} / {close_b}, Parens: {open_p} / {close_p}")
    assert open_b == close_b, f"Braces mismatch: {open_b} vs {close_b}"
    assert open_p == close_p, f"Parens mismatch: {open_p} vs {close_p}"
    print("JSX syntax check PASSED!")
