import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from '../server.mjs';

test('server serves a runnable web entry, health check and blocks private files',async()=>{
 const s=createServer();
 await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));
 try {
  const base=`http://127.0.0.1:${s.address().port}`;
  const index=await fetch(base+'/');
  assert.equal(index.status,200);
  assert.match(await index.text(),/MARKET PULSE/);
  const catalog=await fetch(base+'/assets/catalog.json');
  assert.equal((await catalog.json()).length,30);
  const health=await fetch(base+'/api/health');
  assert.equal((await health.json()).ok,true);
  for(const filename of ['/app.py','/.env.local','/package.json','/requirements.txt','/.streamlit/secrets.toml']) {
   const response=await fetch(base+filename);
   assert.equal(response.status,404,filename);
  }
 }finally{await new Promise((resolve,reject)=>s.close(err=>err?reject(err):resolve()));}
});
