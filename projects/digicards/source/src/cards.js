export const KINDS = ['monster', 'item', 'weapon', 'armour', 'energy'];
export const ELEMENTS = ['Nature', 'Fire', 'Water', 'Earth', 'Dark', 'Light', 'Arcane'];
export const cardSchema = {
  type: 'object', additionalProperties: false,
  required: ['name','kind','element','rarity','cost','description','artPrompt','hp','attack','defence','moves','effect','amount'],
  properties: {
    name: {type:'string',minLength:1,maxLength:40}, kind:{type:'string',enum:KINDS},
    element:{type:'string',enum:ELEMENTS}, rarity:{type:'string',enum:['Common','Uncommon','Rare']},
    cost:{type:'integer',minimum:0,maximum:5}, description:{type:'string',maxLength:180}, artPrompt:{type:'string',maxLength:1200},
    hp:{type:'integer',minimum:0,maximum:60}, attack:{type:'integer',minimum:0,maximum:12}, defence:{type:'integer',minimum:0,maximum:8},
    moves:{type:'array',maxItems:2,items:{type:'object',additionalProperties:false,required:['name','cost','power'],properties:{name:{type:'string',minLength:1,maxLength:30},cost:{type:'integer',minimum:0,maximum:5},power:{type:'integer',minimum:1,maximum:15}}}},
    effect:{type:'string',enum:['none','heal','buff','debuff','attack','defence','energy']}, amount:{type:'integer',minimum:0,maximum:12}
  }
};
export function validateCard(c) {
  const errors=[];
  if (!c || typeof c!=='object' || Array.isArray(c)) return ['Card must be an object.'];
  for (const [key, rule] of Object.entries(cardSchema.properties)) {
    const value=c[key];
    if (rule.type==='string' && (typeof value!=='string' || value.length>(rule.maxLength??2000) || value.length<(rule.minLength??0))) errors.push(`${key}: invalid text.`);
    if (rule.enum && !rule.enum.includes(value)) errors.push(`${key}: choose ${rule.enum.join(', ')}.`);
    if (rule.type==='integer' && (!Number.isInteger(value)||value<rule.minimum||value>rule.maximum)) errors.push(`${key}: must be ${rule.minimum}–${rule.maximum}.`);
  }
  if (!Array.isArray(c.moves)) errors.push('Moves must be a list.');
  else if (c.kind==='monster') {
    if(c.moves.length!==2) errors.push('Monsters require exactly two moves.');
    for(const m of c.moves) if(!m || typeof m.name!=='string'||!m.name.trim()||m.name.length>30||!Number.isInteger(m.cost)||m.cost<0||m.cost>5||!Number.isInteger(m.power)||m.power<1||m.power>15) errors.push('Move requires a name, cost 0–5 and power 1–15.');
    if(c.moves[0]?.cost!==0) errors.push('The first move must cost zero energy.');
    if(c.hp<20||c.attack<1) errors.push('Monsters need at least 20 HP and 1 attack.');
    if(c.effect!=='none'||c.amount!==0) errors.push('Monster effects come from their moves and played cards.');
  } else if(c.moves.length) errors.push('Only monsters have native moves.');
  const allowed={item:['heal','buff','debuff'],weapon:['attack'],armour:['defence'],energy:['energy']};
  if(allowed[c.kind]&&!allowed[c.kind].includes(c.effect)) errors.push(`Invalid effect for ${c.kind}.`);
  if(c.kind!=='monster'&&(c.hp!==0||c.attack!==0||c.defence!==0)) errors.push('Non-monster base stats must be zero.');
  if(c.kind!=='monster'&&c.amount<1) errors.push('The effect amount must be positive.');
  if(c.kind==='energy'&&(c.cost!==0||c.amount!==1)) errors.push('Basic energy is free and adds one capacity.');
  if(c.id!==undefined && !/^[a-z0-9_-]{1,80}$/.test(c.id)) errors.push('Invalid card ID.');
  if(c.art!==undefined && !/^\/(art\/[a-zA-Z0-9_-]+\.png|generated\/[a-zA-Z0-9_-]+\.(png|jpg|webp))$/.test(c.art)) errors.push('Art must be a local card image.');
  return [...new Set(errors)];
}
export function rulesText(c){
  if(c.kind==='monster') return 'Summon to an empty back-board slot.';
  return {heal:`Restore ${c.amount} HP to a friendly monster.`,buff:`Give a friendly monster +${c.amount} attack for 2 of its side’s end steps.`,debuff:`Give the enemy champion −${c.amount} defence for 2 of its side’s end steps.`,attack:`Equip: +${c.amount} attack. Replaces its weapon.`,defence:`Equip: +${c.amount} defence. Replaces its armour.`,energy:'Add 1 energy capacity and 1 available energy. Once per turn; maximum 10.'}[c.effect]||'';
}
export function validateDeck(deck, cards){
  const errors=[], counts={};
  if(!deck||!Array.isArray(deck.cards)) return ['Deck cards must be a list.'];
  if(deck.cards.length!==32) errors.push(`Deck needs 32 cards (currently ${deck.cards.length}).`);
  for(const id of deck.cards){if(!cards.some(c=>c.id===id)) errors.push(`Unknown card: ${id}`);counts[id]=(counts[id]||0)+1;}
  for(const c of cards) if(c.kind!=='energy'&&(counts[c.id]||0)>2) errors.push(`${c.name}: maximum two copies.`);
  if(!deck.cards.includes(deck.champion)||cards.find(c=>c.id===deck.champion)?.kind!=='monster') errors.push('Choose a monster in this deck as champion.');
  return errors;
}
