import test from 'node:test';
import assert from 'node:assert/strict';
import {smoothPoints,chartGeometry,nearestPoint,appendConsole} from '../studio/static/charts.js';

test('EMA preserves steps and skips nonfinite scalars',()=>{
  const points=[{step:0,value:10},{step:50,value:2},{step:100,value:NaN}];
  assert.deepEqual(smoothPoints(points,.5).map(p=>[p.step,p.value]),[[0,10],[50,6]]);
  assert.equal(points[1].value,2);
});
test('constant and single point curves have finite geometry',()=>{
  for(const points of [[{step:0,value:0}],[{step:10,value:2},{step:20,value:2}]]){
    const geometry=chartGeometry(points);
    assert.ok(geometry.maxX>geometry.minX && geometry.maxY>geometry.minY);
    assert.ok(!/NaN|Infinity/.test(geometry.path));
  }
  assert.equal(chartGeometry([]),null);
});
test('hover selects nearest observed step, not an invented value',()=>{
  const points=[{step:50,value:8},{step:100,value:6},{step:150,value:4}];
  assert.equal(nearestPoint(points,130),points[2]);
});
test('console keeps a bounded tail and removes terminal escape codes',()=>{
  assert.deepEqual(appendConsole('123','\x1b[31m456\x1b[0m',4),{text:'3456',trimmed:true});
  assert.equal(appendConsole('','epoch=1\rstep=2\r\n').text,'epoch=1\nstep=2\n');
});
