// =============================================================================
// DỊCH SẴN index.html CHO BẢN EXE (Đợt 0 nâng cấp giao diện — 27/09/2026)
//
// index.html ở gốc project là BẢN NGUỒN: chạy `python server.py` vẫn dùng nó nguyên như cũ
// (React/Tailwind/Babel tải từ CDN, JSX dịch ngay trong trình duyệt — tiện sửa và soi lỗi).
// Bản EXE thì dùng bản dịch sẵn do file này ghi ra thư mục build_web/:
//   - JSX → app.js: dịch lúc build bằng ĐÚNG Babel standalone mà trình duyệt đang dùng, ĐÚNG
//     preset/plugin mặc định của nó cho <script type="text/babel"> (react + env → ES5). Không đổi
//     preset: ES5 biến let/const thành var — code nào lỡ dùng biến trước khi khai báo đang chạy
//     "được" nhờ vậy, đổi sang cú pháp mới là có thể văng lỗi.
//   - Tailwind → app.css: build bằng đúng Tailwind 3.4.17 (bản cdn.tailwindcss.com đang phục vụ),
//     cùng tailwind.config đọc thẳng từ index.html. Đặt cuối <head> — đúng chỗ bản CDN tự chèn
//     <style> của nó — để thứ tự đè CSS y như cũ.
//   - React, ReactDOM, xlsx, font Inter → build_web/vendor/ (mở app không cần internet).
// Chạy: node webbuild/build.js (build_exe.py tự gọi trước PyInstaller).
// =============================================================================
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'index.html');
const OUT = path.join(ROOT, 'build_web');
const NM = path.join(__dirname, 'node_modules');

const pkgVer = (name) => require(path.join(NM, name, 'package.json')).version;
const VER = {
    babel: pkgVer('@babel/standalone'),
    tailwind: pkgVer('tailwindcss'),
    react: pkgVer('react'),
    reactDom: pkgVer('react-dom'),
    xlsx: pkgVer('xlsx'),
};
const VENDOR = {
    react: `vendor/react-${VER.react}.production.min.js`,
    reactDom: `vendor/react-dom-${VER.reactDom}.production.min.js`,
    xlsx: `vendor/xlsx-${VER.xlsx}.full.min.js`,
};

function fail(msg) {
    console.error(`\n[LOI webbuild] ${msg}\n`);
    process.exit(1);
}

// Thay đúng 1 lần — thẻ CDN trong index.html đổi (Gemini/agent khác sửa head) thì DỪNG BUILD,
// không để lọt ra EXE một bản vừa có CDN vừa có bản dịch sẵn.
function replaceOnce(html, find, repl, label) {
    const n = html.split(find).length - 1;
    if (n !== 1) fail(`Tim thay ${n} lan (can dung 1): ${label}\n  -> ${find}`);
    return html.replace(find, () => repl);
}

async function main() {
    let html = fs.readFileSync(SRC, 'utf8');

    // ---- 1. Tách khối JSX + kiểm bản Babel trình duyệt đang dùng khớp bản build ----
    const babelTag = `<script src="https://unpkg.com/@babel/standalone@${VER.babel}/babel.min.js"></script>`;
    if (!html.includes(babelTag)) fail(`index.html khong con dung Babel ${VER.babel} — cap nhat webbuild/package.json cho khop.`);
    const jsxRe = /<script type="text\/babel">([\s\S]*?)<\/script>/g;
    const blocks = [...html.matchAll(jsxRe)];
    if (blocks.length !== 1) fail(`Can dung 1 khoi <script type="text/babel">, dang co ${blocks.length}.`);

    // ---- 2. Dịch JSX: options chép từ buildBabelOptions() của Babel standalone (script không type=module) ----
    const Babel = require('@babel/standalone');
    const t0 = Date.now();
    const js = Babel.transform(blocks[0][1], {
        filename: 'Inline Babel script',
        presets: ['react', 'env'],
        plugins: ['transform-class-properties', 'transform-object-rest-spread', 'transform-flow-strip-types'],
        targets: { browsers: undefined },
    }).code;
    const tBabel = Date.now() - t0;

    // ---- 3. Tailwind: config lấy thẳng từ dòng `tailwind.config = {...}` trong index.html ----
    const cfgMatch = html.match(/tailwind\.config\s*=\s*(\{.*\})\s*$/m);
    if (!cfgMatch) fail('Khong tim thay dong `tailwind.config = {...}` trong index.html.');
    const userCfg = new Function(`return (${cfgMatch[1]});`)();
    const postcss = require('postcss');
    const tailwind = require('tailwindcss');
    const t1 = Date.now();
    const { css } = await postcss([tailwind({ ...userCfg, content: [{ raw: html, extension: 'html' }] })])
        .process('@tailwind base;\n@tailwind components;\n@tailwind utilities;\n', { from: undefined });
    const tTw = Date.now() - t1;

    // ---- 4. Ghép index.html bản EXE ----
    const fontCss = fs.readFileSync(path.join(__dirname, 'fonts', 'google-inter.css'), 'utf8')
        .replace(/url\(https:\/\/fonts\.gstatic\.com\/s\/inter\/(v\d+)\/([^)]+)\)/g, (_, v, f) => `url(vendor/fonts/inter-${v}-${f})`);
    if (/fonts\.gstatic\.com/.test(fontCss)) fail('Con URL fonts.gstatic.com chua doi sang file local.');

    html = replaceOnce(html, '<script src="https://cdn.tailwindcss.com"></script>', '', 'Tailwind CDN');
    html = replaceOnce(html, '<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>',
        `<script src="${VENDOR.react}"></script>`, 'React');
    html = replaceOnce(html, '<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>',
        `<script src="${VENDOR.reactDom}"></script>`, 'ReactDOM');
    html = replaceOnce(html, babelTag, '', 'Babel');
    // xlsx chỉ dùng trong nút bấm xuất file → defer, khỏi chặn lượt vẽ đầu
    html = replaceOnce(html, `<script src="https://cdn.jsdelivr.net/npm/xlsx@${VER.xlsx}/dist/xlsx.full.min.js"></script>`,
        `<script defer src="${VENDOR.xlsx}"></script>`, 'xlsx');
    html = replaceOnce(html, '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">',
        `<style>\n${fontCss}</style>`, 'Google Fonts Inter');
    html = replaceOnce(html, '</head>', '<link rel="stylesheet" href="app.css">\n</head>', '</head>');
    html = replaceOnce(html, blocks[0][0], '<script src="app.js"></script>', 'khoi text/babel');
    for (const bad of ['cdn.tailwindcss.com', 'unpkg.com', 'cdn.jsdelivr.net', 'fonts.googleapis.com', '<script type="text/babel"']) {
        if (html.includes(bad)) fail(`Ban EXE con sot "${bad}".`);
    }

    // ---- 5. Ghi ra build_web/ ----
    // Dọn NỘI DUNG chứ không xoá chính thư mục: có cửa sổ lệnh đang đứng trong build_web/ là Windows báo EPERM
    fs.mkdirSync(OUT, { recursive: true });
    for (const f of fs.readdirSync(OUT)) fs.rmSync(path.join(OUT, f), { recursive: true, force: true });
    fs.mkdirSync(path.join(OUT, 'vendor', 'fonts'), { recursive: true });
    fs.writeFileSync(path.join(OUT, 'index.html'), html);
    fs.writeFileSync(path.join(OUT, 'app.js'), js);
    fs.writeFileSync(path.join(OUT, 'app.css'), css);
    fs.copyFileSync(path.join(NM, 'react/umd/react.production.min.js'), path.join(OUT, VENDOR.react));
    fs.copyFileSync(path.join(NM, 'react-dom/umd/react-dom.production.min.js'), path.join(OUT, VENDOR.reactDom));
    fs.copyFileSync(path.join(NM, 'xlsx/dist/xlsx.full.min.js'), path.join(OUT, VENDOR.xlsx));
    for (const f of fs.readdirSync(path.join(__dirname, 'fonts')).filter(f => f.endsWith('.woff2'))) {
        fs.copyFileSync(path.join(__dirname, 'fonts', f), path.join(OUT, 'vendor', 'fonts', f));
    }

    const kb = (f) => (fs.statSync(path.join(OUT, f)).size / 1024).toFixed(0) + ' KB';
    console.log(`[webbuild] Babel ${VER.babel} (${tBabel} ms) · Tailwind ${VER.tailwind} (${tTw} ms) · React ${VER.react} · xlsx ${VER.xlsx}`);
    console.log(`[webbuild] build_web/index.html ${kb('index.html')} · app.js ${kb('app.js')} · app.css ${kb('app.css')}`);
}

main().catch((e) => fail(e && e.stack || String(e)));
