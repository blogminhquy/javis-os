const fs = require('fs');
const assert = require('assert');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../../dashboard/console.js'), 'utf8');
const fn = source.match(/  async function _vtAddFolder\(rel, isDir\) \{[\s\S]*?\n  \}/)[0];
async function run(rel, isDir, name, ok = true) {
  const calls = [], reveals = [], errors = [];
  const add = new Function('prompt','FormData','fbrain','fetch','_vtRevealInTree','alert','window',fn+';return _vtAddFolder')(
    () => name, FormData, () => 'brain', async (url, opts) => {
      calls.push({url, fields: Object.fromEntries(opts.body)});
      return {ok, json: async () => ok ? {ok:true} : {error:'Cannot create'}};
    }, async (...args) => reveals.push(args), msg => errors.push(msg), {t:k=>k});
  await add(rel, isDir); return {calls, reveals, errors};
}
(async () => {
  const folder = await run('brain/Parent', true, 'Child');
  assert.equal(folder.calls[0].url, '/files/mkdir');
  assert.deepStrictEqual(folder.calls[0].fields, {brain:'brain',path:'brain/Parent',name:'Child'});
  assert.deepStrictEqual(folder.reveals, [['brain/Parent/Child',true]]);
  const file = await run('brain/Parent/note.md', false, 'Sibling');
  assert.equal(file.calls[0].fields.path, 'brain/Parent');
  const cancel = await run('brain', true, null); assert.equal(cancel.calls.length,0);
  const error = await run('brain', true, 'Child', false);
  assert.equal(error.reveals.length,0); assert.deepStrictEqual(error.errors,['Cannot create']);
  console.log('OK create folder uses selected parent; cancellation and failures are safe');
})().catch(e=>{console.error(e);process.exit(1)});
