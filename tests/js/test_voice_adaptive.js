const assert = require('node:assert/strict');
const fs = require('fs');
assert.ok(fs.existsSync('dashboard/voice-adaptive.js'), 'adaptive controller must exist');
const {Controller} = require('../../dashboard/voice-adaptive.js');
let now = 0;
const make = () => new Controller({now: () => now});
let c = make();
c.update('Ý là'); now = 4000;
assert.equal(c.tick().some(x => x.type === 'commit'), false);
assert.equal(c.state, 'HOLD'); now = 10000;
assert.equal(c.tick()[0].type, 'save_draft');
assert.equal(c.text, 'Ý là');
c.resume(); c.update('Ý là anh muốn mở khung chat giúp anh'); now += 1400;
assert.equal(c.tick()[0].type, 'commit');
assert.deepEqual(c.tick(), []);
c.update('Ý là anh muốn mở khung chat giúp anh'); now+=1400;
assert.equal(c.tick()[0].type,'commit','same command in a new utterance still responds');
now = 0; c = make(); c.update('Mở khung chat giúp anh');
for (let i=0;i<100;i++) { now += 5; c.update('Mở khung chat giúp anh'); }
now = 900; assert.equal(c.tick()[0].type, 'commit');
now = 0; c = make(); c.update('Khoan để anh nghĩ'); now=20000;
assert.equal(c.tick().some(x=>x.type==='commit'), false);
now=90000; assert.equal(c.tick()[0].type, 'save_draft');
for (const text of ['Không', 'Vâng', 'Vâng anh hiểu rồi', 'anh hiểu rồi', 'Vâng nhưng kiểm tra lại giúp anh', 'Đừng chờ nữa, mở chat đi', 'Có đúng không?']) {
  now=0; c=make(); c.update(text); now=2200;
  assert.equal(c.tick()[0].type, 'commit', text);
}
for (const text of ['em', 'anh muốn em', 'có phải là', 'khi anh nói thì']) {
  now=0; c=make(); c.update(text); now=4000;
  assert.equal(c.tick().some(x=>x.type==='commit'), false, text);
}
now=0; c=make(); c.update('Mở chat'); now=750; c.tick();
assert.equal(c.state,'READY'); c.update('Mở chat và'); now=950;
assert.equal(c.tick().some(x=>x.type==='commit'),false);
c.save('hidden'); now=100000; assert.deepEqual(c.tick(),[]);
assert.equal(c.submit()[0].text,'Mở chat và');
now=0; c=make(); c.update('a'.repeat(4001)); assert.equal(c.state,'SAVED_DRAFT');
assert.equal(c.text.length,4001); assert.deepEqual(c.resume(),[]);
c.reset(); assert.equal(c.text,'');
now=0; c=make();
for(let i=0;i<9;i++) { now+=1500; c.update('Anh muốn '+ 'nói '.repeat(i+1)); }
assert.equal(c.samples.length,8); assert.ok(c.delay >=1200 && c.delay<=2200);
assert.ok(c.samples.every(x=>x===1500));
c.resetLearning(); assert.equal(c.samples.length,0);
for(let i=0;i<250;i++) { now+=10; c.update('bí mật '+i); }
assert.ok(c.diagnostics().length<=200);
assert.equal(JSON.stringify(c.diagnostics()).includes('bí mật'),false);
console.log('adaptive policy/controller scenarios passed');
