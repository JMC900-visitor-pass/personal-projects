import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {Readable} from 'node:stream';
import os from 'node:os';
import path from 'node:path';
import {createApp} from '../server/index.js';
import {generateCard,fillWorkflow,basicWorkflow} from '../server/providers.js';
import {seedCards} from '../src/seed.js';

// Exercise the real HTTP handler without opening ports or contacting external services.
function request(app,url,{method='GET',body,headers={}}={}){
  return new Promise(resolve=>{
    const req=Readable.from(body===undefined?[]:[JSON.stringify(body)]);
    Object.assign(req,{url,method,headers:{host:'127.0.0.1:4317',...(body===undefined?{}:{'content-type':'application/json'}),...headers}});
    const responseHeaders={};let status=200;
    const res={setHeader(k,v){responseHeaders[k.toLowerCase()]=v;},writeHead(code,h={}){status=code;for(const [k,v]of Object.entries(h))responseHeaders[k.toLowerCase()]=v;},end(value){const text=String(value??'');resolve({status,headers:responseHeaders,text,json:()=>JSON.parse(text)});}};
    app.emit('request',req,res);
  });
}
test('API validates and persists cards/deck while denying cross-origin writes and private files',async()=>{
  const dir=await mkdtemp(path.join(os.tmpdir(),'digicards-test-'));
  try{
    let app=await createApp({dataDir:dir,generatedDir:path.join(dir,'images')});
    const post=(route,body,headers={})=>request(app,route,{method:'POST',body,headers});
    const library=(await request(app,'/api/library')).json();
    assert.equal(library.cards.length,13);
    assert.equal((await request(app,'/')).status,200);
    assert.equal((await request(app,'/src/battle.js')).status,200);
    assert.equal((await request(app,'/server/index.js')).status,404);
    assert.equal((await request(app,'/api/settings',{headers:{host:'hostile.example'}})).status,403);
    assert.equal((await post('/api/cards',{}, {origin:'https://evil.example'})).status,403);
    assert.equal((await post('/api/cards',{})).status,422);
    const c=structuredClone(seedCards[0]);delete c.id;c.name='Test card';
    const created=await post('/api/cards',c);assert.equal(created.status,201);assert.ok(created.json().id.startsWith('card_'));
    assert.equal((await post('/api/deck',{...library.deck,cards:[]})).status,422);
    assert.equal((await post('/api/deck',{...library.deck,name:'Saved deck'})).status,200);
    app=await createApp({dataDir:dir,generatedDir:path.join(dir,'images')});
    const restored=(await request(app,'/api/library')).json();assert.equal(restored.cards.length,14);assert.equal(restored.deck.name,'Saved deck');
  }finally{await rm(dir,{recursive:true,force:true});}
});
test('Ollama adapter requests schema, validates model output and rejects malformed responses',async t=>{
  let bad=false,seen;
  t.mock.method(globalThis,'fetch',async(url,options)=>{assert.equal(new URL(url).pathname,'/api/generate');seen=JSON.parse(options.body);return Response.json({response:bad?'not json':JSON.stringify(seedCards[0])});});
  const c=await generateCard({ollamaURL:'http://model.test',model:'fixture'},'Forest guardian','monster');
  assert.equal(c.name,'Grove Sentinel');assert.equal(seen.stream,false);assert.ok(seen.format.properties.moves);
  bad=true;await assert.rejects(()=>generateCard({ollamaURL:'http://model.test',model:'fixture'},'Forest','monster'),/valid card JSON/);
});
test('workflow placeholders preserve prompt text without injecting nodes',()=>{
  const template=basicWorkflow('test.safetensors'),prompt='A "guardian"\nwith branches';
  const result=fillWorkflow(template,prompt,123);assert.equal(result['6'].inputs.text,prompt);assert.equal(result['3'].inputs.seed,123);
  assert.equal(template['6'].inputs.text,'{{prompt}}');assert.throws(()=>fillWorkflow({nodes:[]},prompt,1));
});
test('image API submits workflow, polls history and persists returned artwork',async t=>{
  const dir=await mkdtemp(path.join(os.tmpdir(),'digicards-image-test-'));let received;
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    const endpoint=new URL(url).pathname;
    if(endpoint==='/prompt'){received=JSON.parse(options.body);return Response.json({prompt_id:'p1'});}
    if(endpoint==='/history/p1')return Response.json({p1:{outputs:{9:{images:[{filename:'out.png',subfolder:'',type:'output'}]}},status:{completed:true}}});
    if(endpoint==='/view')return new Response(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l1sAAAAASUVORK5CYII=','base64'),{headers:{'Content-Type':'image/png'}});
    throw Error('Unexpected provider endpoint');
  });
  try{
    const app=await createApp({dataDir:dir,generatedDir:path.join(dir,'images')});
    const post=async(route,body)=>{const r=await request(app,route,{method:'POST',body});assert.ok(r.status<300,r.text);return r.json();};
    await post('/api/settings',{ollamaURL:'http://model.test',comfyURL:'http://image.test',checkpoint:'fixture',model:'fixture'});
    const job=await post('/api/generate/image',{prompt:'A guardian'});
    const output=(await request(app,'/api/image-jobs/'+job.id)).json();
    assert.equal(output.status,'complete');assert.match(output.art,/^\/generated\//);assert.equal(received.prompt['6'].inputs.text,'A guardian');
    assert.equal((await request(app,output.art)).headers['content-type'],'image/png');
  }finally{await rm(dir,{recursive:true,force:true});}
});
test('provider connection failures return actionable states instead of claiming readiness',async t=>{
  t.mock.method(globalThis,'fetch',async()=>{throw new TypeError('Failed to fetch');});
  const dir=await mkdtemp(path.join(os.tmpdir(),'digicards-offline-test-'));
  try{const app=await createApp({dataDir:dir,generatedDir:path.join(dir,'images')});const response=(await request(app,'/api/connections')).json();assert.equal(response.ollama.connected,false);assert.equal(response.comfy.connected,false);assert.match(response.ollama.error,/unavailable/);}finally{await rm(dir,{recursive:true,force:true});}
});
