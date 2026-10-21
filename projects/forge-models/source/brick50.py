import bpy,math,html
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from collections import defaultdict
bpy.ops.wm.read_factory_settings(use_empty=True)
s=bpy.context.scene;s.name='Brick 50 • Assembled';ROOT='/path/to/project/forge/'
col=bpy.data.collections.new('Brickwork • individual units');s.collection.children.link(col)
mat=bpy.data.materials.new('Firebrick');mat.diffuse_color=(.62,.43,.27,1)
def mesh(name,vs,fs):
 m=bpy.data.meshes.new(name);m.from_pydata(vs,[],fs);m.update();o=bpy.data.objects.new(name,m);col.objects.link(o);o.data.materials.append(mat);return o
def box(name,x0,x1,y0,y1,z0,z1):
 g=.0007;x0+=g;x1-=g;y0+=g;y1-=g;z0+=g;z1-=g
 return mesh(name,[(x,y,z) for z in [z0,z1] for y in [y0,y1] for x in [x0,x1]],[(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)])
# Four segmented hearth strips leave a central bottom-air opening.
for y0,y1 in [(-.25,-.035),(.035,.25)]:
 for a,b in [(-.25,-.125),(-.125,0),(0,.125),(.125,.25)]:box('Hearth brick',a,b,y0,y1,0,.06)
for a,b in [(-.25,-.035),(.035,.25)]:box('Hearth / air opening',a,b,-.035,.035,0,.06)
# Alternate overlapping corner bonds on the U-shaped chamber.
for row in range(4):
 z0=.06+row*.06;z1=z0+.06
 if row%2==0:
  for side in [-1,1]:
   x0,x1=(-.25,-.15) if side<0 else (.15,.25)
   for a,b in [(-.25,-.10),(-.10,.05),(.05,.15)]:box('Wall course '+str(row+1),x0,x1,a,b,z0,z1)
  for a,b in [(-.25,-.0833),(-.0833,.0833),(.0833,.25)]:box('Rear bonded corner',a,b,.15,.25,z0,z1)
 else:
  for side in [-1,1]:
   x0,x1=(-.25,-.15) if side<0 else (.15,.25)
   for a,b in [(-.25,-.175),(-.175,-.025),(-.025,.125),(.125,.25)]:box('Wall staggered course '+str(row+1),x0,x1,a,b,z0,z1)
  for a,b in [(-.15,0),(0,.15)]:box('Rear infill bond',a,b,.15,.25,z0,z1)
# Radial wedge bricks form a self-supporting arch concept over the opening.
for row in range(5):
 ya=-.25+row*.10;yb=ya+.10
 for k in range(11):
  if row==3 and k in [4,5,6]:continue
  a=k*math.pi/11+.003;b=(k+1)*math.pi/11-.003
  vs=[]
  for y in [ya+.0007,yb-.0007]:
   for r,t in [(.15,a),(.21,a),(.21,b),(.15,b)]:vs.append((r*math.cos(t),y,.30+r*math.sin(t)))
  mesh('Arch wedge / row %d brick %d'%(row+1,k+1),vs,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
# Brick haunches rest on the side walls beside the barrel vault.
for side in [-1,1]:
 for row in range(5):
  ya=-.25+row*.1
  if side>0:box('Outer shoulder',.21,.25,ya,ya+.1,.30,.34)
  else:box('Outer shoulder',-.25,-.21,ya,ya+.1,.30,.34)
# Chimney saddle follows the curved roof; its interior remains open.
def saddle(name,x0,x1,y0,y1):
 xs=[x0+(x1-x0)*i/8 for i in range(9)];vs=[]
 for y in [y0+.0007,y1-.0007]:
  for x in xs:vs.append((x,y,.30+math.sqrt(.21**2-x*x)))
  for x in xs:vs.append((x,y,.565))
 fs=[]
 for i in range(8):fs += [(i,i+1,9+i+1,9+i),(18+i,27+i,27+i+1,18+i+1),(i,18+i,18+i+1,i+1),(9+i,9+i+1,27+i+1,27+i)]
 fs.extend([(0,9,27,18),(8,26,35,17)]);mesh(name,vs,fs)
saddle('Chimney saddle / front',-.12,.12,-.02,.04)
saddle('Chimney saddle / rear',-.12,.12,.16,.22)
saddle('Chimney saddle / left',-.12,-.06,.04,.16)
saddle('Chimney saddle / right',.06,.12,.04,.16)
for row in range(3):
 z0=.565+row*.06;z1=z0+.06
 if row%2==0:
  for ya,yb in [(-.02,.04),(.16,.22)]:
   for xa,xb in [(-.12,0),(0,.12)]:box('Chimney course',xa,xb,ya,yb,z0,z1)
  for xa,xb in [(-.12,-.06),(.06,.12)]:box('Chimney side',xa,xb,.04,.16,z0,z1)
 else:
  for xa,xb in [(-.12,-.06),(.06,.12)]:
   for ya,yb in [(-.02,.10),(.10,.22)]:box('Chimney corner bond',xa,xb,ya,yb,z0,z1)
  for ya,yb in [(-.02,.04),(.16,.22)]:box('Chimney infill',-.06,.06,ya,yb,z0,z1)
objs=list(col.objects)
s.unit_settings.system='METRIC';s.unit_settings.length_unit='CENTIMETERS'
s['Concept']='50 × 50 cm footprint • brick-only stacked masonry concept'
s['Assembly']='Staggered corners; radial arch bricks; shaped chimney saddle; bonded chimney courses.'
s['Interior']='Open hearth, bottom air aperture, barrel roof and open chimney throat. Metalwork and fuel omitted.'
bpy.ops.object.camera_add(location=(1.05,-1.45,1.05));cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,.34))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=1.05;s.camera=cam
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':
   area.spaces.active.shading.type='WIREFRAME';area.spaces.active.region_3d.view_perspective='CAMERA'
bpy.ops.wm.save_as_mainfile(filepath=ROOT+'forge-brick-50.blend')
# Vector drawing export: bold visible edges + optional fine hidden wire.
parts=[]
def add(t):parts.append(t)
def text(x,y,t,size=18,color='#c8eaff'):add(f'<text x="{x}" y="{y}" font-family="Arial,Helvetica,sans-serif" font-size="{size}" fill="{color}">{html.escape(t)}</text>')
def line(x,y,xx,yy,dash=''):add(f'<path d="M{x},{y}L{xx},{yy}" stroke="#77a8c8" stroke-width="1" fill="none" stroke-dasharray="{dash}"/>')
def start(w,h):
 parts.clear();add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><pattern id="g" width="25" height="25" patternUnits="userSpaceOnUse"><path d="M25 0H0V25" fill="none" stroke="#23465e" stroke-width=".5"/></pattern></defs><rect width="100%" height="100%" fill="#102c43"/><rect x="25" y="25" width="{w-50}" height="{h-50}" fill="url(#g)" stroke="#6f9bb8"/>')
def save(name):add('</svg>');open(ROOT+name+'.svg','w').write('\n'.join(parts))
def draw(direction,rect,wire=False,chosen=None):
 use=objs if chosen is None else chosen
 bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();deps.update();d=Vector(direction).normalized();right=Vector((0,0,1)).cross(d).normalized() if abs(d.z)<.99 else Vector((1,0,0));up=d.cross(right).normalized()
 bv=[];bf=[]
 for ob in use:
  offset=len(bv);bv.extend([developer@example.invalid for v in ob.data.vertices]);bf.extend([tuple(offset+i for i in f.vertices) for f in ob.data.polygons])
 tree=BVHTree.FromPolygons(bv,bf)
 edges=[];points=[]
 for o in use:
  vs=[developer@example.invalid for v in o.data.vertices];adj=defaultdict(list)
  for f in o.data.polygons:
   for k in f.edge_keys:adj[tuple(sorted(k))].append(f.normal)
  for e in o.data.edges:
   a,b=e.vertices;ns=adj[tuple(sorted((a,b)))];crease=len(ns)!=2 or ns[0].dot(ns[1])<.995
   if not crease:continue
   edges.append((vs[a],vs[b]));points.extend([vs[a],vs[b]])
 x,y,w,h=rect;xs=[p.dot(right) for p in points];ys=[p.dot(up) for p in points];scale=min(w*.9/(max(xs)-min(xs)),h*.9/(max(ys)-min(ys)));cx=(max(xs)+min(xs))/2;cy=(max(ys)+min(ys))/2
 def project(p):return x+w/2+(p.dot(right)-cx)*scale,y+h/2-(p.dot(up)-cy)*scale
 visible=[];allpaths=[]
 for a,b in edges:
  aa=project(a);bb=project(b);allpaths.append(f'M{aa[0]:.2f},{aa[1]:.2f}L{bb[0]:.2f},{bb[1]:.2f}')
  n=16;run=None
  for i in range(n+1):
   p=a.lerp(b,i/n);loc,normal,index,distance=tree.ray_cast(p+d*3,-d,3.002);vis=loc is None or (loc-p).length<.002
   if vis and run is None:run=i
   if (not vis or i==n) and run is not None:
    end=i if vis else i-1
    if end>run:
     q=project(a.lerp(b,run/n));r=project(a.lerp(b,end/n));visible.append(f'M{q[0]:.2f},{q[1]:.2f}L{r[0]:.2f},{r[1]:.2f}')
    run=None
 if wire:add('<path d="'+' '.join(allpaths)+'" fill="none" stroke="#66a5ce" stroke-width=".65" opacity=".48"/>')
 add('<path d="'+' '.join(visible)+'" fill="none" stroke="#d4f0ff" stroke-width="1.15"/>');return project
start(1600,1500);text(65,85,'BRICK / 50',38);text(65,122,'50 × 50 cm  •  BRICK-ONLY WIREFRAME',18);line(65,145,1535,145)
draw((3,-5,3),(110,180,1380,1190),True)
text(65,1445,'Fine lines reveal the hearth, bottom air opening and chimney throat.',18);save('forge-brick-50-wireframe')
start(2400,1700);text(65,87,'BRICK / 50',40);text(65,124,'BARE MASONRY CONCEPT  /  50 × 50 cm FOOTPRINT',18);text(1920,88,'B50  •  BLUEPRINT 01',20);line(60,150,2340,150)
text(65,202,'01  FRONT / BRICK ARCH',21);text(625,202,'02  RIGHT ELEVATION',21)
p=draw((0,-1,0),(65,230,485,620));a=p(Vector((-.25,-.25,0)));b=p(Vector((.25,-.25,0)));yy=850;line(a[0],a[1],a[0],yy+10);line(b[0],b[1],b[0],yy+10);line(a[0],yy,b[0],yy);text((a[0]+b[0])/2-25,yy-10,'50 cm',16)
draw((1,0,0),(625,230,485,620));line(60,895,1130,895)
text(65,940,'03  HEARTH PLAN / ROOF REMOVED',21)
# Hide everything above hearth course for a clear plan view.
removed=[o for o in objs if not o.name.startswith('Hearth')]
for o in removed:o.hide_set(True)
p=draw((0,0,1),(125,975,840,420),False,[o for o in objs if o not in removed]);text(85,1435,'Central opening continues down through the hearth.',17)
for o in removed:o.hide_set(False)
line(1170,178,1170,1480);text(1220,202,'04  INTERIOR / CUTAWAY',21);text(1220,235,'Near-side masonry removed for viewing',17)
# Presentation cut removes right half while retaining the complete rear.
removed=[o for o in objs if sum(v.co.x for v in o.data.vertices)/len(o.data.vertices)>.055 and sum(v.co.y for v in o.data.vertices)/len(o.data.vertices)<.16]
for o in removed:o.hide_set(True)
p=draw((3,-5,2.8),(1200,280,1130,1100),False,[o for o in objs if o not in removed])
for o in removed:o.hide_set(False)
line(60,1500,2340,1500)
text(70,1548,'STACKING',18);text(70,1581,'Staggered wall joints and overlapping corners.',17)
text(860,1548,'ROOF',18);text(860,1581,'Radial wedge bricks form the arched chamber.',17)
text(1650,1548,'CHIMNEY',18);text(1650,1581,'Shaped saddle with alternating brick courses.',17)
text(70,1645,'VISUAL CONCEPT  •  INDIVIDUAL BRICKS  •  OPEN INTERIOR',15);save('forge-brick-50-blueprint')
print('BRICK CONCEPT COMPLETE',len(objs),'bricks')
