// Offline render of the OS template's grub.cfg with the same nunjucks call the platform uses
// (nunjucks.compile with the default environment), against a fixture of the OS-install context.
// Usage: NODE_PATH=<dir containing nunjucks> node render-grub.js <grub.cfg> <context.json> > rendered.cfg
const fs = require('fs');
const nunjucks = require('nunjucks');

const [templatePath, contextPath] = process.argv.slice(2);
const template = nunjucks.compile(fs.readFileSync(templatePath, 'utf8'));
process.stdout.write(template.render(JSON.parse(fs.readFileSync(contextPath, 'utf8'))));
