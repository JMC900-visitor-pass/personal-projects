import {validateDeck} from './cards.js';
function rng(s){let x=s.rng|0;x^=x<<13;x^=x>>>17;x^=x<<5;s.rng=x>>>0;return s.rng/4294967296;}
function shuffle(s,a){for(let i=a.length-1;i>0;i--){const j=Math.floor(rng(s)*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;}
const def=(s,copy)=>s.catalog[copy.id];
const unit=(s,copy)=>({...copy,hp:def(s,copy).hp,weapon:null,armour:null,mods:[]});
const log=(s,message)=>{s.log.push(message);s.log=s.log.slice(-60);};
export function stat(s,u,key){return Math.max(0,def(s,u)[key]+(key==='attack'&&u.weapon?def(s,u.weapon).amount:0)+(key==='defence'&&u.armour?def(s,u.armour).amount:0)+u.mods.filter(m=>m.stat===key).reduce((n,m)=>n+m.amount,0));}
export function newBattle(deck,cards,seed=Date.now()){
  const errors=validateDeck(deck,cards);if(errors.length)throw Error(errors.join(' '));
  const s={version:1,rng:(seed>>>0)||1,catalog:Object.fromEntries(cards.map(c=>[c.id,structuredClone(c)])),turn:0,number:1,phase:'main',winner:null,pending:null,log:[],sides:[]};
  for(let i=0;i<2;i++){
    const copies=deck.cards.map((id,n)=>({id,uid:`${i}-${n}`}));
    const champ=copies.splice(copies.findIndex(c=>c.id===deck.champion),1)[0];
    shuffle(s,copies);
    s.sides.push({name:i?'The Hollow':'You',champion:unit(s,champ),back:[],deck:copies,hand:copies.splice(0,5),discard:[],energyZone:[],energy:1,capacity:1,energyPlayed:false,mulligan:true,acted:false});
  }
  log(s,'Duel begins. Prepare your board; first player cannot attack on turn 1.');return s;
}
function getTarget(p,uid){return [p.champion,...p.back].find(u=>u?.uid===uid);}
function defeat(s,side){
  const p=s.sides[side];
  if(p.champion?.hp>0)return;
  if(p.champion){const u=p.champion;p.discard.push({id:u.id,uid:u.uid});for(const slot of ['weapon','armour'])if(u[slot])p.discard.push(u[slot]);p.champion=null;log(s,`${def(s,u).name} falls.`);}
  if(!p.back.length){s.winner=1-side;log(s,`${s.sides[s.winner].name} win the duel.`);}
  else{s.pending=side;log(s,`${p.name}: choose a back monster to promote.`);}
}
function nextTurn(s){
  const p=s.sides[s.turn];
  for(const u of [p.champion,...p.back].filter(Boolean))u.mods=u.mods.filter(m=>--m.ends>0);
  s.turn=1-s.turn;s.number++;s.phase='main';const next=s.sides[s.turn];next.energy=next.capacity;next.energyPlayed=false;next.acted=false;next.mulligan=false;
  if(!next.deck.length){s.winner=1-s.turn;log(s,`${next.name} cannot draw. Deck exhausted.`);return;}
  next.hand.push(next.deck.shift());log(s,`${next.name} draw a card. Turn ${s.number}.`);
}
function apply(s,a){
  if(s.winner!==null)throw Error('The duel is over. Start a new duel.');
  const p=s.sides[s.turn], enemy=s.sides[1-s.turn];
  if(s.pending!==null){
    if(a.type!=='promote')throw Error('Choose a monster to promote first.');
    const side=s.sides[s.pending],idx=side.back.findIndex(u=>u.uid===a.uid);
    if(idx<0)throw Error('Choose a living back monster.');
    side.champion=side.back.splice(idx,1)[0];s.pending=null;log(s,`${def(s,side.champion).name} is promoted.`);return;
  }
  if(a.type==='discard'){
    if(s.phase!=='cleanup')throw Error('Discard only during cleanup.');
    const idx=p.hand.findIndex(c=>c.uid===a.uid);if(idx<0)throw Error('Choose a card in hand.');
    p.discard.push(p.hand.splice(idx,1)[0]);if(p.hand.length<=7)nextTurn(s);return;
  }
  if(s.phase==='cleanup')throw Error('Choose cards to discard down to seven.');
  if(a.type==='mulligan'){
    if(!p.mulligan||p.acted)throw Error('Mulligan is only available before your first play.');
    p.deck.push(...p.hand);shuffle(s,p.deck);p.hand=p.deck.splice(0,5);p.mulligan=false;log(s,`${p.name} replace their opening hand.`);return;
  }
  if(a.type==='play'){
    if(s.phase!=='main'||p.acted)throw Error('Play cards before your champion action.');
    const idx=p.hand.findIndex(c=>c.uid===a.uid);if(idx<0)throw Error('Card is not in hand.');
    const copy=p.hand[idx],c=def(s,copy);if(p.energy<c.cost)throw Error('Not enough energy.');
    if(c.kind==='energy'){
      if(p.energyPlayed||p.capacity>=10)throw Error('One energy per turn; capacity is capped at ten.');
      p.capacity++;p.energy++;p.energyPlayed=true;p.energyZone.push(copy);
    }else if(c.kind==='monster'){
      if(p.back.length>=3)throw Error('The three back-board slots are full.');p.back.push(unit(s,copy));
    }else{
      const target=c.effect==='debuff'?enemy.champion:getTarget(p,a.target||p.champion?.uid);
      if(!target)throw Error('Choose a valid monster target.');
      if(c.kind==='weapon'||c.kind==='armour'){if(target[c.kind])p.discard.push(target[c.kind]);target[c.kind]=copy;}
      else{
        if(c.effect==='heal')target.hp=Math.min(def(s,target).hp,target.hp+c.amount);
        if(c.effect==='buff'||c.effect==='debuff')target.mods.push({stat:c.effect==='buff'?'attack':'defence',amount:c.effect==='buff'?c.amount:-c.amount,ends:2,source:c.name});
        p.discard.push(copy);
      }
    }
    p.energy-=c.cost;p.hand.splice(idx,1);p.mulligan=false;log(s,`${p.name} play ${c.name}.`);return;
  }
  if(a.type==='attack'){
    if(p.acted)throw Error('Your champion has already acted.');
    if(s.number===1)throw Error('The first player cannot attack on turn 1.');
    const move=def(s,p.champion).moves[a.index];if(!move)throw Error('Choose one of your two moves.');
    if(p.energy<move.cost)throw Error('Not enough energy for that move.');
    const damage=Math.max(1,stat(s,p.champion,'attack')+move.power-stat(s,enemy.champion,'defence'));
    p.energy-=move.cost;enemy.champion.hp=Math.max(0,enemy.champion.hp-damage);p.acted=true;p.mulligan=false;s.phase='action';
    log(s,`${def(s,p.champion).name}: ${move.name} deals ${damage} damage.`);defeat(s,1-s.turn);return;
  }
  if(a.type==='swap'){
    if(p.acted)throw Error('Your champion has already acted.');const idx=p.back.findIndex(c=>c.uid===a.uid);if(idx<0)throw Error('Choose a back monster.');
    [p.champion,p.back[idx]]=[p.back[idx],p.champion];p.acted=true;p.mulligan=false;s.phase='action';log(s,`${def(s,p.champion).name} takes the front.`);return;
  }
  if(a.type==='end'){
    p.mulligan=false;
    if(p.hand.length>7){s.phase='cleanup';log(s,'Discard to seven cards.');}else nextTurn(s);return;
  }
  throw Error('Unknown duel action.');
}
export function act(state,action){const next=structuredClone(state);try{apply(next,action);return {state:next,error:null};}catch(e){return {state,error:e.message};}}
// The opponent only examines its own hand and public board, never the player's hand or either deck order.
export function aiAction(s){
  if(s.pending===1)return {type:'promote',uid:s.sides[1].back[0].uid};
  if(s.pending===0||s.turn!==1||s.winner!==null)return null;
  const p=s.sides[1];if(s.phase==='cleanup')return {type:'discard',uid:p.hand[0].uid};
  if(!p.acted){
    const energy=p.hand.find(x=>def(s,x).kind==='energy');
    if(energy&&!p.energyPlayed&&p.capacity<10)return {type:'play',uid:energy.uid};
    const summon=p.hand.find(x=>def(s,x).kind==='monster'&&def(s,x).cost<=p.energy);
    if(summon&&p.back.length<3)return {type:'play',uid:summon.uid};
    const useful=p.hand.find(x=>{const c=def(s,x);return c.cost<=p.energy&&(c.kind==='weapon'&&!p.champion.weapon||c.kind==='armour'&&!p.champion.armour||c.effect==='heal'&&p.champion.hp<def(s,p.champion).hp||['buff','debuff'].includes(c.effect));});
    if(useful)return {type:'play',uid:useful.uid};
    const moves=def(s,p.champion).moves;return {type:'attack',index:moves[1].cost<=p.energy?1:0};
  }
  return {type:'end'};
}
export function zoneCards(s,side){const p=s.sides[side],units=[p.champion,...p.back].filter(Boolean);return [...p.deck,...p.hand,...p.discard,...p.energyZone,...units.flatMap(u=>[u,...[u.weapon,u.armour].filter(Boolean)])];}
