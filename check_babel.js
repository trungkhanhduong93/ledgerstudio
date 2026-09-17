const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
const match = html.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
if (!match) {
    console.error("Could not find script type=text/babel");
    process.exit(1);
}
const code = match[1];
const parser = require('./node_modules/@babel/parser');
try {
    parser.parse(code, { sourceType: 'module', plugins: ['jsx'] });
    console.log("Babel JSX parse SUCCESSFUL!");
} catch (err) {
    console.error("Babel JSX parse ERROR:", err.message, "at line", err.loc);
    process.exit(1);
}
