import sys
with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace("                                    )}", "                                    ) : null}")

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
