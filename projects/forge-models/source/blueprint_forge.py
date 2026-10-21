import bpy, math, html
from mathutils import Vector
from collections import defaultdict
ROOT='/path/to/project/forge/'
s=bpy.context.scene;s.name='Forge • Assembled reference'
# A separate scene preserves the assembled concept inside the blueprint project.
bpy.ops.scene.new(type='FULL_COPY');s=bpy.context.scene;s.name='Forge • Exploded assemblies'
objs=[o for o in s.objects if o.type=='MESH' and not any(c.name.startswith(('00','05')) for c in o.users_collection)]
for o in s.objects:
 if any(c.name.startswith(('00','05')) for c in o.users_collection):o.hide_set(True)
base={o:o.location.copy() for o in objs}
parts=[]
def add(t):parts.append(t)
def text(x,y,t,size=18,fill='#c4e7fa',weight='400',spacing=0):add(f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{weight}" letter-spacing="{spacing}" fill="{fill}">{html.escape(t)}</text>')
def line(x1,y1,x2,y2,color='#5588ab',w=1,dash=''):add(f'<path d="M{x1},{y1}L{x2},{y2}" stroke="{color}" stroke-width="{w}" fill="none"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
add('<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="1680" viewBox="0 0 2400 1680">')
add('<defs><pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="#204663" stroke-width="0.55"/></pattern></defs>')
add('<rect width="2400" height="1680" fill="#102e48"/><rect x="30" y="30" width="2340" height="1620" fill="url(#grid)" stroke="#79accb" stroke-width="1.5"/>')
text(70,94,'COAL FORGE',42,weight='700',spacing=5);text(72,128,'ASSEMBLY STUDY  /  EXISTING CONCEPT',16,spacing=3)
text(1840,86,'CF–01  /  DESIGN SHEET',20,weight='700');text(1840,118,'ORTHOGRAPHIC + EXPLODED VIEWS',14,spacing=1.5)
line(60,151,2340,151);line(1050,175,1050,1325);line(65,805,1025,805)
text(75,195,'01  FRONT ELEVATION',19,weight='700',spacing=1.5)
text(575,195,'02  RIGHT ELEVATION',19,weight='700',spacing=1.5)
text(75,843,'03  PLAN / TOP VIEW',19,weight='700',spacing=1.5)
text(1090,195,'04  EXPLODED SYSTEM',19,weight='700',spacing=1.5)
text(1090,224,'Separated for clarity • all original components retained',15,fill='#85b4d0')
# Use silhouette/crease edges and ray visibility, avoiding triangulation clutter.
def drawview(direction,rect,margin=.06):
 bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();deps.update()
 d=Vector(direction).normalized();right=Vector((0,0,1)).cross(d).normalized() if abs(d.z)<.99 else Vector((1,0,0));up=d.cross(right).normalized()
 geo=[];pts=[]
 for o in objs:
  # Unmodified topology supplies clean design edges; bevels are retained in the model.
  m=o.data;world=o.matrix_world;vs=[developer@example.invalid for v in m.vertices];norm=[(world.to_3x3()@p.normal).normalized() for p in m.polygons];adj=defaultdict(list)
  for p in m.polygons:
   for a,b in p.edge_keys:adj[tuple(sorted((a,b)))].append(p.index)
  for e in m.edges:
   a,b=e.vertices;ns=[norm[i] for i in adj[tuple(sorted((a,b)))]]
   silhouette=len(ns)<2 or (ns[0].dot(d)*ns[1].dot(d)<0)
   crease=len(ns)>1 and ns[0].dot(ns[1])<.85
   if not (silhouette or crease):continue
   geo.append((vs[a],vs[b]));pts.extend([vs[a],vs[b]])
 xs=[p.dot(right) for p in pts];ys=[p.dot(up) for p in pts];x0,y0,w,h=rect
 scale=min(w*(1-margin*2)/(max(xs)-min(xs)),h*(1-margin*2)/(max(ys)-min(ys)))
 cx=(max(xs)+min(xs))/2;cy=(max(ys)+min(ys))/2
 def project(p):return (x0+w/2+(p.dot(right)-cx)*scale,y0+h/2-(p.dot(up)-cy)*scale)
 paths=[]
 for a,b in geo:
  count=max(3,min(22,int((b-a).length*35)));run=None
  for i in range(count+1):
   p=a.lerp(b,i/count);hit,loc,*_=s.ray_cast(deps,p+d*12,-d,distance=12.025)
   vis=(not hit) or (loc-p).length<.024
   if vis and run is None:run=i
   if (not vis or i==count) and run is not None:
    end=i if vis else i-1
    if end>run:
     p1=project(a.lerp(b,run/count));p2=project(a.lerp(b,end/count));paths.append(f'M{p1[0]:.2f},{p1[1]:.2f}L{p2[0]:.2f},{p2[1]:.2f}')
    run=None
 add('<path d="'+' '.join(paths)+'" fill="none" stroke="#d0efff" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/>')
 return project
p=drawview((0,-1,0),(65,230,455,535));line(82,750,508,750,color='#5785a4',dash='8 7')
p=drawview((1,0,0),(565,230,455,535));line(582,750,1008,750,color='#5785a4',dash='8 7')
p=drawview((0,0,1),(120,870,800,380));text(95,1301,'Hood footprint shown above hearth and chassis.',15,fill='#85b4d0')
# Explode only through transforms. No mesh changes.
for o in objs:
 n=o.name
 if n.startswith(('Open chimney','Chimney seam')):o.location.z+=1.22
 elif n.startswith(('Tapered smoke','Hood front')):o.location.z+=.84
 elif n.startswith(('Back firebrick','Back skin')):o.location+=Vector((0,.24,.43))
 elif n.startswith(('Side firebrick','Steel cheek','Front corner','Cheek fastening')):o.location+=Vector((.22 if o.location.x>0 else -.22,0,.43))
 elif n.startswith(('Cast iron','Tuyere grate','Coal /','Workpiece')):o.location.z+=.22
 elif any(c.name.startswith('03') for c in o.users_collection):o.location+=Vector((.75,0,-.04))
proj=drawview((3,-5,2.8),(1130,255,1000,1060),.045)
def callout(num,point,x,y):
 px,py=proj(Vector(point));line(px,py,x-30,y,color='#81c2e8',w=1.1);line(x-30,y,x-15,y,color='#81c2e8');add(f'<circle cx="{px}" cy="{py}" r="3" fill="#c4e7fa"/><circle cx="{x}" cy="{y}" r="18" fill="#102e48" stroke="#a4d5f2" stroke-width="1.4"/>');text(x-10,y+6,num,16,weight='700')
callout('A1',(0,.2,3.5),2180,324)
callout('A2',(.55,-.23,2.35),2245,534)
callout('A3',(.87,.06,1.57),2250,777)
callout('A4',(0,0,1.14),1120,785)
callout('A5',(1.74,0,.52),2250,1110)
callout('A6',(.61,-.43,.40),1980,1300)
line(60,1350,2340,1350)
text(75,1392,'COMPONENT KEY',16,weight='700',spacing=2)
items=[('A1','FLUE','Chimney tube + seam bands'),('A2','SMOKE HOOD','Tapered shell + front lip'),('A3','HEARTH ENCLOSURE','Firebrick + steel cheeks'),('A4','FIRE BED','Coal + firepot + tuyere grate'),('A5','AIR & ASH','Blower + feed + damper + cleanout'),('A6','CHASSIS','Table + legs + braces + shelf')]
for i,(n,title,desc) in enumerate(items):
 x=75+(i%3)*770;y=1440+(i//3)*91
 text(x,y,n,20,weight='700');text(x+55,y,title,17,weight='700',spacing=1);text(x+55,y+27,desc,16,fill='#92bdd6')
line(60,1600,2340,1600);text(75,1630,'VISUAL CONCEPT  /  COMPONENT RELATIONSHIPS  /  NO DIMENSIONS',13,spacing=2);text(2000,1630,'CF–01     •     01 / 01',15,weight='700')
add('</svg>');open(ROOT+'forge-blueprint.svg','w').write('\n'.join(parts))
# Reset studio visibility and frame exploded model in its own scene.
for o in s.objects:
 if any(c.name.startswith('05') for c in o.users_collection):o.hide_set(False)
s.camera.location=(4.6,-6.3,4.2);s.camera.rotation_euler=(Vector((.3,0,1.75))-s.camera.location).to_track_quat('-Z','Y').to_euler();s.camera.data.ortho_scale=4.9
s['Design note']='Visual assembly study of the existing forge concept. Parts are separated by transforms only.'
s.render.filepath=ROOT+'forge-exploded.png'
bpy.ops.wm.save_as_mainfile(filepath=ROOT+'forge-blueprint.blend')
print('BLUEPRINT COMPLETE',len(objs),'mesh components')
