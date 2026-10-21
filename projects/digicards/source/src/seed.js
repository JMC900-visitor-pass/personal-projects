const base={rarity:'Common',description:'',artPrompt:'',hp:0,attack:0,defence:0,moves:[],effect:'none',amount:0};
const monster=(id,name,element,art,hp,attack,defence,moves)=>({...base,id,name,kind:'monster',element,cost:2,art,hp,attack,defence,moves,description:'A creature drawn from the world beyond the cards.',artPrompt:`${name}, ${element} fantasy creature, confident clean ink outlines, graphic cel shading, isolated character portrait, no text or card frame`});
const move=(name,cost,power)=>({name,cost,power});
const card=(id,name,kind,element,cost,effect,amount,art)=>({...base,id,name,kind,element,cost,effect,amount,...(art?{art}:{}),artPrompt:`${name}, fantasy ${kind}, bold ink illustration, isolated object, no text`});
export const seedCards=[
monster('grove','Grove Sentinel','Nature','/art/grove.png',44,6,4,[move('Bark strike',0,5),move('Rootbreaker',2,12)]),
monster('ember','Ember Familiar','Fire','/art/ember.png',32,9,2,[move('Cinder bite',0,4),move('Flare',2,13)]),
monster('gloom','Gloomwing','Dark','/art/gloom.png',35,8,3,[move('Night dust',0,5),move('Eclipse',3,15)]),
monster('stone','Stone Warden','Earth','/art/stone.png',52,5,6,[move('Rock fist',0,3),move('Fault line',3,12)]),
card('mend','Wild Remedy','item','Nature',1,'heal',12,'/art/remedy.png'),
card('surge','Battlecry','item','Fire',1,'buff',4),
card('fracture','Fracture','item','Dark',1,'debuff',3),
card('tonic','Spring Tonic','item','Water',1,'heal',8),
card('fang','Fangblade','weapon','Earth',2,'attack',4,'/art/fang.png'),
card('brand','Ember Brand','weapon','Fire',1,'attack',2),
card('plate','Chitin Guard','armour','Earth',2,'defence',3,'/art/plate.png'),
card('veil','Moonveil','armour','Arcane',1,'defence',2),
card('energy','Primal Energy','energy','Arcane',0,'energy',1)
];
export const seedDeck={name:'Into the overgrowth',champion:'grove',cards:[...seedCards.filter(c=>c.kind!=='energy').flatMap(c=>[c.id,c.id]),...Array(8).fill('energy')]};
