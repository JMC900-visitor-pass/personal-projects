import {cardSchema,validateCard} from '../src/cards.js';
export async function providerJSON(base,path,body,timeout=10000){
  let r;try{r=await fetch(new URL(path,base),{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(timeout)});}catch(e){throw Error(`Model service unavailable or timed out. Check Connections and that the service is running. (${e.name})`);}
  if(!r.ok)throw Error(`Model service returned HTTP ${r.status}. Check model and workflow settings.`);
  const data=await r.json();if(data.error)throw Error(typeof data.error==='string'?data.error:'Model rejected the request.');return data;
}
export async function generateCard(settings,brief,kind){
  if(!settings.model)throw Error('Choose an installed Ollama model in Connections first.');
  const result=await providerJSON(settings.ollamaURL,'/api/generate',{model:settings.model,stream:false,format:cardSchema,
    system:'Create a playable Digicards card as JSON matching the schema. No invented mechanics. Exactly two damage moves for monsters; first move costs 0. Monster hp 20–60, attack 1–12, defence 0–8, effect none, amount 0. Non-monsters have hp/attack/defence 0 and no moves. Item effect heal/buff/debuff. Weapon effect attack. Armour effect defence. Energy effect energy, amount 1, cost 0. All other amounts 1–12. Use a vivid artPrompt describing only the subject, no text or frame. Buffs/debuffs last 2 affected-side end steps. Description is flavour only.',
    prompt:`Card kind: ${kind}. Creative brief: ${brief}`,options:{temperature:0.7}},180000);
  let card;try{card=JSON.parse(result.response);}catch{throw Error('The model did not return valid card JSON. Try another draft or model.');}
  if(card.kind!==kind)throw Error('The model returned the wrong card kind. Generate again.');
  const errors=validateCard(card);if(errors.length)throw Error(`Draft needs repair: ${errors.join(' ')}`);
  return card;
}
export function fillWorkflow(template,prompt,seed){
  let found=false;
  const visit=x=>{
    if(Array.isArray(x))return x.map(visit);
    if(x&&typeof x==='object')return Object.fromEntries(Object.entries(x).map(([k,v])=>[k,visit(v)]));
    if(typeof x==='string'){if(x.includes('{{prompt}}'))found=true;return x==='{{seed}}'?seed:x.replaceAll('{{prompt}}',prompt);}
    return x;
  };
  const workflow=visit(template);
  if(!found)throw Error('Workflow needs {{prompt}} in its positive text input.');
  if(!workflow||Array.isArray(workflow)||!Object.values(workflow).every(n=>n&&typeof n.class_type==='string'&&n.inputs&&typeof n.inputs==='object'))throw Error('Use a ComfyUI API-format workflow, not the editor layout JSON.');
  return workflow;
}
export function basicWorkflow(checkpoint){return {
  '3':{class_type:'KSampler',inputs:{seed:'{{seed}}',steps:20,cfg:7,sampler_name:'euler',scheduler:'normal',denoise:1,model:['4',0],positive:['6',0],negative:['7',0],latent_image:['5',0]}},
  '4':{class_type:'CheckpointLoaderSimple',inputs:{ckpt_name:checkpoint}},
  '5':{class_type:'EmptyLatentImage',inputs:{width:512,height:640,batch_size:1}},
  '6':{class_type:'CLIPTextEncode',inputs:{text:'{{prompt}}',clip:['4',1]}},
  '7':{class_type:'CLIPTextEncode',inputs:{text:'text, watermark, logo, card border, blurry',clip:['4',1]}},
  '8':{class_type:'VAEDecode',inputs:{samples:['3',0],vae:['4',2]}},
  '9':{class_type:'SaveImage',inputs:{filename_prefix:'Digicards',images:['8',0]}}
};}
