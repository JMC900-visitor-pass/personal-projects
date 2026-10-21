import http from 'node:http';
import {readFile,writeFile,mkdir,rename,access} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {seedCards,seedDeck} from '../src/seed.js';
import {validateCard,validateDeck,KINDS} from '../src/cards.js';
import {providerJSON,generateCard,fillWorkflow,basicWorkflow} from './providers.js';
const root=fileURLToPath(new URL('../',import.meta.url));
export async function createApp({dataDir=path.join(root,'data'),generatedDir=path.join(root,'public/generated')}={}){
  await mkdir(dataDir,{recursive:true});await mkdir(generatedDir,{recursive:true});
  const load=async(name,fallback)=>{try{return JSON.parse(await readFile(path.join(dataDir,name),'utf8'));}catch(e){if(e.code==='ENOENT')return structuredClone(fallback);throw e;}};
  let library=await load('library.json',seedCards),deck=await load('deck.json',seedDeck),settings=await load('settings.json',{ollamaURL:'http://127.0.0.1:11434',model:'',comfyURL:'http://127.0.0.1:8188',checkpoint:'',workflow:null});
  const save=async(name,data)=>{const temp=path.join(dataDir,`${name}.${randomUUID()}.tmp`);await writeFile(temp,JSON.stringify(data,null,2));await rename(temp,path.join(dataDir,name));};
  const jobs=new Map();let queue=Promise.resolve();
  const serial=fn=>{const result=queue.then(fn);queue=result.catch(()=>{});return result;};
  function json(res,status,data){res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));}
  async function body(req){let data='';for await(const chunk of req){data+=chunk;if(Buffer.byteLength(data)>1024*1024)throw Error('Request too large.');}return JSON.parse(data||'{}');}
  function localURL(value){const u=new URL(value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash)throw Error('Use an HTTP service URL without credentials or query parameters.');return u.origin;}
  return http.createServer(async(req,res)=>{
    res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'");
    try{
      const origin=`http://${req.headers.host}`;
      if(!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(req.headers.host||'')){json(res,403,{error:'Local host only.'});return;}
      if(req.headers.origin&&req.headers.origin!==origin){json(res,403,{error:'Cross-origin requests are not allowed.'});return;}
      if(req.method==='POST'&&!req.headers['content-type']?.startsWith('application/json')){json(res,415,{error:'Use application/json.'});return;}
      const url=new URL(req.url,origin),route=url.pathname;
      if(route==='/api/library'&&req.method==='GET'){json(res,200,{cards:library,deck});return;}
      if(route==='/api/settings'&&req.method==='GET'){json(res,200,settings);return;}
      if(route==='/api/settings'&&req.method==='POST'){
        const b=await body(req);const next={ollamaURL:localURL(b.ollamaURL),comfyURL:localURL(b.comfyURL),model:String(b.model||'').slice(0,160),checkpoint:String(b.checkpoint||'').slice(0,240),workflow:b.workflow||null};
        if(next.workflow)fillWorkflow(next.workflow,'Validation',1);
        await serial(async()=>{await save('settings.json',next);settings=next;});json(res,200,settings);return;
      }
      if(route==='/api/connections'&&req.method==='GET'){
        const current={...settings};const results=await Promise.allSettled([providerJSON(current.ollamaURL,'/api/tags'),providerJSON(current.comfyURL,'/object_info/CheckpointLoaderSimple')]);
        json(res,200,{ollama:results[0].status==='fulfilled'?{connected:true,models:(results[0].value.models||[]).map(m=>m.name)}:{connected:false,error:results[0].reason.message},comfy:results[1].status==='fulfilled'?{connected:true,checkpoints:results[1].value.CheckpointLoaderSimple?.input?.required?.ckpt_name?.[0]||[]}:{connected:false,error:results[1].reason.message}});return;
      }
      if(route==='/api/cards'&&req.method==='POST'){
        const raw=await body(req);const allowed=['name','kind','element','rarity','cost','description','artPrompt','hp','attack','defence','moves','effect','amount','art'];
        const card=Object.fromEntries(allowed.filter(k=>raw[k]!==undefined).map(k=>[k,raw[k]]));const errors=validateCard(card);if(errors.length){json(res,422,{error:errors.join(' ')});return;}
        if(card.art){const imagePath=card.art.startsWith('/generated/')?path.join(generatedDir,path.basename(card.art)):path.join(root,'public',card.art);try{await access(imagePath);}catch{throw Error('The selected artwork is missing.');}}
        card.id=`card_${randomUUID().replaceAll('-','')}`;
        await serial(async()=>{const next=[...library,card];await save('library.json',next);library=next;});json(res,201,card);return;
      }
      if(route==='/api/deck'&&req.method==='POST'){
        const b=await body(req);const next={name:String(b.name||'My deck').slice(0,60),champion:b.champion,cards:b.cards};const errors=validateDeck(next,library);if(errors.length){json(res,422,{error:errors.join(' ')});return;}
        await serial(async()=>{await save('deck.json',next);deck=next;});json(res,200,deck);return;
      }
      if(route==='/api/generate/card'&&req.method==='POST'){
        const b=await body(req);if(!KINDS.includes(b.kind)||typeof b.brief!=='string'||!b.brief.trim()||b.brief.length>3000)throw Error('Supply a card kind and a brief of 1–3000 characters.');
        json(res,200,await generateCard({...settings},b.brief,b.kind));return;
      }
      if(route==='/api/generate/image'&&req.method==='POST'){
        const b=await body(req);if(typeof b.prompt!=='string'||!b.prompt.trim()||b.prompt.length>2000)throw Error('Write an art prompt of 1–2000 characters.');
        const current=structuredClone(settings);if(!current.workflow&&!current.checkpoint)throw Error('Choose a ComfyUI checkpoint or import an API workflow in Connections.');
        const workflow=fillWorkflow(current.workflow||basicWorkflow(current.checkpoint),b.prompt,Math.floor(Math.random()*1e12));
        const result=await providerJSON(current.comfyURL,'/prompt',{prompt:workflow,client_id:randomUUID()},20000);
        if(!result.prompt_id)throw Error('ComfyUI did not return a job ID.');
        const id=randomUUID();jobs.set(id,{base:current.comfyURL,promptId:result.prompt_id,created:Date.now()});
        for(const [key,j]of jobs)if(Date.now()-j.created>86400000)jobs.delete(key);
        json(res,202,{id,status:'queued'});return;
      }
      if(route.startsWith('/api/image-jobs/')&&req.method==='GET'){
        const job=jobs.get(route.split('/').at(-1));if(!job){json(res,404,{error:'Image job not found; it may predate a server restart.'});return;}
        if(job.art){json(res,200,{status:'complete',art:job.art});return;}
        const history=await providerJSON(job.base,`/history/${encodeURIComponent(job.promptId)}`);const run=history[job.promptId];
        if(run?.status?.status_str==='error')throw Error('Image generation failed in ComfyUI. Inspect its workflow and model.');
        const image=Object.values(run?.outputs||{}).flatMap(o=>o.images||[]).find(i=>i.type==='output');
        if(!image){if(run?.status?.completed)throw Error('Workflow completed without a saved image. Include a SaveImage output.');json(res,200,{status:'running'});return;}
        const r=await fetch(new URL(`/view?${new URLSearchParams({filename:image.filename,subfolder:image.subfolder||'',type:'output'})}`,job.base),{signal:AbortSignal.timeout(30000)});
        if(!r.ok)throw Error('Could not retrieve generated artwork.');
        const mime=r.headers.get('content-type')?.split(';')[0],ext={'image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[mime];if(!ext)throw Error('Image service returned an unsupported image format.');
        const bytes=Buffer.from(await r.arrayBuffer());if(bytes.length>20*1024*1024)throw Error('Generated artwork exceeds 20 MB.');
        const file=`${randomUUID()}.${ext}`;await writeFile(path.join(generatedDir,file),bytes,{flag:'wx'});job.art=`/generated/${file}`;json(res,200,{status:'complete',art:job.art});return;
      }
      if(req.method!=='GET'){json(res,404,{error:'Unknown endpoint.'});return;}
      let pathname=decodeURIComponent(route);let target;
      if(pathname.startsWith('/src/'))target=path.resolve(root,'.'+pathname);
      else if(pathname.startsWith('/generated/'))target=path.resolve(generatedDir,pathname.slice('/generated/'.length));
      else target=path.resolve(root,'public',pathname==='/'?'index.html':'.'+pathname);
      const roots=[path.join(root,'public'),path.join(root,'src'),generatedDir];
      if(!roots.some(base=>target.startsWith(base+path.sep)))throw Error('Invalid file path.');
      let file;try{file=await readFile(target);}catch{json(res,404,{error:'Not found.'});return;}
      const mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp'}[path.extname(target)];
      if(!mime){json(res,404,{error:'Not found.'});return;}
      res.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-cache'});res.end(file);
    }catch(e){json(res,400,{error:e.message});}
  });
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const server=await createApp();const port=Number(process.env.DIGICARDS_PORT||4317);
  server.listen(port,'127.0.0.1',()=>console.log(`Digicards is ready at http://127.0.0.1:${port}`));
}
