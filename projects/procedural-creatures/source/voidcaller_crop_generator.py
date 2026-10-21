from PIL import Image, ImageDraw
import random, os, json

GRID=16; SCALE=10; NUM_CROPS=120; MASTER_SEED=20260902
OUTPUT_DIR=r"E:\project\voidcaller_crops"; BG=(8,10,14,255)

PALETTES={
"Ember":((120,65,30),(232,92,38),(255,191,74)),
"Tide":((31,91,125),(61,174,199),(166,236,244)),
"Volt":((110,103,24),(235,210,33),(255,249,144)),
"Verdant":((39,102,48),(92,177,76),(246,141,196)),
"Terra":((92,67,44),(157,112,66),(240,190,101)),
"Gale":((65,105,105),(137,190,181),(224,250,245)),
"Radiant":((136,119,49),(229,204,91),(255,247,184)),
"Umbral":((66,39,88),(137,70,166),(226,129,244)),
"Astral":((57,48,119),(117,80,193),(239,126,235)),
"Ethereal":((42,104,91),(92,190,157),(205,255,237)),
"Wild":((101,72,34),(157,151,57),(245,132,62)),
"Mystic":((76,43,118),(151,78,201),(128,215,247))
}
FLOWERS=["star","cross","cup","orb","crown","bell"]
LEAVES=["single","paired","wide","spike","fan"]
FRUITS=["none","berry","pod","bulb","crystal"]

def put(g,x,y,c):
    if 0<=x<GRID and 0<=y<GRID:g[y][x]=c
def blank(): return [[None]*GRID for _ in range(GRID)]
def render(g):
    im=Image.new("RGBA",(GRID,GRID),BG)
    for y,row in enumerate(g):
        for x,c in enumerate(row):
            if c: im.putpixel((x,y),(*c,255))
    return im

def dna(seed):
    r=random.Random(seed)
    return dict(seed=seed,family=r.choice(list(PALETTES)),height=r.randint(7,12),
      branches=r.randint(1,4),leaf=r.choice(LEAVES),leaf_size=r.randint(1,3),
      flower=r.choice(FLOWERS),flowers=r.randint(1,4),fruit=r.choice(FRUITS),
      fruits=r.randint(1,3),lean=r.choice([-1,0,0,0,1]),mutation=r.random(),
      sparkle=r.random(),symmetry=r.uniform(.65,1))

def seed_img(d):
    r=random.Random(d["seed"]+1); dark,mid,bright=PALETTES[d["family"]]; g=blank()
    shape=r.randrange(4)
    pts=[[(7,7),(8,7),(7,8),(8,8),(7,9)],
         [(6,7),(7,7),(8,8),(9,8),(7,9),(8,9)],
         [(7,6),(7,7),(8,7),(7,8),(8,8),(8,9)],
         [(6,8),(7,7),(8,7),(9,8),(7,9),(8,9)]][shape]
    for p in pts:put(g,*p,mid)
    put(g,*pts[0],bright)
    return render(g)

def leaf(g,x,y,direction,d,p,r):
    dark,mid,bright=p; c=mid; n=d["leaf_size"]; s=d["leaf"]
    put(g,x,y,c)
    if s=="single":
        for i in range(1,n+1):put(g,x+direction*i,y-i//2,c)
    elif s=="paired":
        for i in range(1,n+1):put(g,x+direction*i,y,c);put(g,x+direction*i,y-1,c)
    elif s=="wide":
        for dx,dy in [(direction,0),(direction,-1),(2*direction,-1)]:put(g,x+dx,y+dy,c)
    elif s=="spike":
        for i in range(1,n+1):put(g,x+direction*i,y-i,c)
    else:
        for dx,dy in [(direction,0),(direction,-1),(2*direction,-1),(direction,1)]:put(g,x+dx,y+dy,c)

def flower(g,x,y,d,p):
    dark,mid,bright=p;s=d["flower"]
    shapes={"star":[(0,0),(-1,0),(1,0),(0,-1),(0,1)],
    "cross":[(0,0),(-1,-1),(1,-1),(-1,1),(1,1)],
    "cup":[(-1,0),(0,1),(1,0),(0,0)],
    "orb":[(0,0),(-1,0),(1,0),(0,-1)],
    "crown":[(-1,0),(0,-1),(1,0),(-1,-1),(1,-1)],
    "bell":[(-1,0),(0,0),(1,0),(0,1),(0,2)]}
    for dx,dy in shapes[s]:put(g,x+dx,y+dy,bright)
    put(g,x,y,(255,245,190))

def fruit(g,x,y,d,p):
    s=d["fruit"]; dark,mid,bright=p
    if s=="none":return
    pts={"berry":[(0,0),(1,0),(0,1)],"pod":[(0,0),(0,1),(0,2)],
         "bulb":[(0,0),(-1,1),(0,1),(1,1),(0,2)],
         "crystal":[(0,-1),(-1,0),(0,0),(1,0),(0,1)]}[s]
    for dx,dy in pts:put(g,x+dx,y+dy,bright)

def plant(d,stage):
    r=random.Random(d["seed"]+stage*997);p=PALETTES[d["family"]];g=blank()
    maturity=[0,.28,.55,.78,1][stage];h=max(2,int(d["height"]*maturity));root=14;top=root-h
    put(g,7,14,p[0]);put(g,8,14,p[0])
    if stage>=2:put(g,6,15,p[0]);put(g,9,15,p[0])
    stem=[]
    for i,y in enumerate(range(root,top-1,-1)):
        x=7+int((i/max(1,h))*d["lean"]*2);stem.append((x,y));put(g,x,y,p[0])
    if stage==1:
        x,y=stem[-1];leaf(g,x,y,-1,d,p,r);leaf(g,x,y,1,d,p,r);return render(g)
    br=random.Random(d["seed"]+333);cand=stem[2:-1] or stem
    count=min(len(cand),max(1,int(d["branches"]*maturity)))
    pos=br.sample(cand,count) if cand else [];tips=[]
    for i,(x,y) in enumerate(pos):
        direction=-1 if i%2==0 else 1;length=1+int(maturity*br.randint(1,3));bx,by=x,y
        for j in range(1,length+1):
            bx=x+direction*j;by=y-j//2;put(g,bx,by,p[0])
        tips.append((bx,by));leaf(g,bx,by,direction,d,p,r)
        if br.random()<d["symmetry"]:leaf(g,x,y,-direction,d,p,r)
    tx,ty=stem[-1];leaf(g,tx,ty,-1,d,p,r);leaf(g,tx,ty,1,d,p,r)
    sites=[stem[-1]]+tips
    if stage>=3:
        for fx,fy in sites[:d["flowers"]]:put(g,fx,fy-1,p[2])
    if stage==4:
        for fx,fy in sites[:d["flowers"]]:flower(g,fx,fy-1,d,p)
        for fx,fy in tips[::-1][:d["fruits"]]:fruit(g,fx,fy+1,d,p)
        if d["mutation"]>.78:
            for _ in range(1+int(d["mutation"]*3)):put(g,r.randrange(1,15),r.randrange(1,11),p[2])
        if d["sparkle"]>.82:
            for _ in range(3):put(g,r.randrange(2,14),r.randrange(1,10),(240,245,255))
    return render(g)

def sheet(rows,path):
    cell=88;lw=110;stages=["SEED","SPROUT","YOUNG","MATURE","FLOWER"]
    im=Image.new("RGB",(lw+cell*5,28+len(rows)*cell),(16,18,23));dr=ImageDraw.Draw(im)
    for j,s in enumerate(stages):dr.text((lw+j*cell+15,8),s,fill=(230,230,235))
    for i,(d,imgs) in enumerate(rows):
        y=28+i*cell;dr.text((5,y+15),d["family"],fill=(235,235,240))
        dr.text((5,y+31),str(d["seed"]),fill=(135,140,150));dr.text((5,y+47),d["flower"],fill=(175,180,190))
        for j,x in enumerate(imgs):im.paste(x.resize((72,72),Image.Resampling.NEAREST).convert("RGB"),(lw+j*cell+8,y+4))
    im.save(path)

def generate(output=OUTPUT_DIR,count=NUM_CROPS):
    os.makedirs(output,exist_ok=True);master=random.Random(MASTER_SEED);meta=[];rows=[]
    for i in range(count):
        s=master.randrange(1,2147483647);d=dna(s);folder=os.path.join(output,f"{i:03}_{d['family'].lower()}_{s}");os.makedirs(folder,exist_ok=True)
        imgs=[seed_img(d)]+[plant(d,j) for j in range(1,5)]
        for name,img in zip(["seed","sprout","young","mature","flowering"],imgs):
            img.save(os.path.join(folder,name+".png"))
        with open(os.path.join(folder,"dna.json"),"w") as f:json.dump(d,f,indent=2)
        meta.append(d)
        if len(rows)<24:rows.append((d,imgs))
    with open(os.path.join(output,"crop_dna.json"),"w") as f:json.dump(meta,f,indent=2)
    sheet(rows,os.path.join(output,"crop_growth_sheet.png"))
    print("Generated",count,"crops:",output)

if __name__=="__main__":generate()
