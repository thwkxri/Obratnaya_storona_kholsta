const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.resolve(__dirname, '..');
const ctx = {console, URLSearchParams, setTimeout, clearTimeout, performance,
 document:{getElementById(){return null}, querySelector(){return null}}, location:{search:''}};
ctx.window=ctx;
vm.createContext(ctx);
for (const f of ['story.js','engine/expression.js','engine/resource-path-policy.js','engine/story-loader.js'])
 vm.runInContext(fs.readFileSync(path.join(root,'game',f),'utf8'), ctx, {filename:f});
if(ctx.PARSE_ERRORS.length) { console.error(ctx.PARSE_ERRORS.slice(0,8)); process.exit(1); }
fs.writeFileSync(path.join(__dirname,'parsed_story.json'),JSON.stringify(ctx.STORY,null,2));
console.log('Parsed:',ctx.STORY.scenes.length,'scenes;',Object.keys(ctx.STORY.assets.characters).length,'characters');
console.log('First actions:',JSON.stringify(ctx.STORY.scenes[0].actions.slice(0,7)));
