html = open('index.html', 'r', encoding='utf-8').read()
try:
    code = html.split('<script type="text/babel">')[1].split('</script>')[0]
    open('temp.jsx', 'w', encoding='utf-8').write(code)
except Exception as e:
    print(e)
