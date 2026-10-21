import bpy, math, random
from mathutils import Vector
random.seed(17)
# Preserve the source geometry in a hidden collection.
s=bpy.context.scene
orig=bpy.data.collections.new('00 • Original blockout (hidden)');s.collection.children.link(orig)
for o in list(s.objects):
 for c in list(o.users_collection):c.objects.unlink(o)
 orig.objects.link(o)
orig.hide_render=True;orig.hide_viewport=True

def collection(name):
 c=bpy.data.collections.new(name);s.collection.children.link(c);return c
C=collection('01 • Forged steel chassis')
def finish(o,name,mat):
 o.name=name
 for c in list(o.users_collection):c.objects.unlink(o)
 C.objects.link(o)
 if mat:o.data.materials.append(mat)
 return o
def material(name,color,metal=0,rough=.6):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 n=m.node_tree.nodes;p=n.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
 noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=65;noise.inputs['Detail'].default_value=3
 bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.23;bump.inputs['Distance'].default_value=.012
 m.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);m.node_tree.links.new(bump.outputs['Normal'],p.inputs['Normal'])
 ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.2;ramp.color_ramp.elements[0].color=(*(v*.35 for v in color),1);ramp.color_ramp.elements[1].position=.8;ramp.color_ramp.elements[1].color=(*color,1)
 m.node_tree.links.new(noise.outputs['Fac'],ramp.inputs[0]);m.node_tree.links.new(ramp.outputs[0],p.inputs['Base Color']);return m
steel=material('Blackened rolled steel',(.11,.14,.16),.8,.48)
rust=material('Oxidized edges',(.26,.105,.04),.65,.68)
bolt=material('Oiled hardware',(.23,.25,.26),.85,.34)
brick=material('Warm refractory firebrick',(.55,.38,.22),0,.95)
coal=material('Anthracite',(.026,.029,.033),.2,.84)
ground=material('Workshop concrete',(.13,.15,.16),0,.91)
def box(name,loc,dim,mat=steel,bev=.008):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);finish(o,name,mat)
 if bev:
  m=o.modifiers.new('Soft worn edges','BEVEL');m.width=bev;m.segments=3;o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
 return o
def cyl(name,loc,r,depth,mat=steel,axis=(0,0,1),verts=48):
 bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=r,depth=depth,location=loc);o=bpy.context.object;o.rotation_euler=Vector(axis).to_track_quat('Z','Y').to_euler();finish(o,name,mat)
 m=o.modifiers.new('Machined rim','BEVEL');m.width=.003;m.segments=2;o.modifiers.new('Normals','WEIGHTED_NORMAL');return o
def beam(name,a,b,width,mat=steel):
 d=Vector(b)-Vector(a);o=box(name,(Vector(a)+Vector(b))/2,(width,width,d.length),mat,.003);o.rotation_euler=d.to_track_quat('Z','Y').to_euler();return o
def mesh(name,vs,fs,mat):
 m=bpy.data.meshes.new(name);m.from_pydata(vs,[],fs);m.update();o=bpy.data.objects.new(name,m);C.objects.link(o);o.data.materials.append(mat);return o
def pipe(name,a,b,r,mat=steel):
 d=Vector(b)-Vector(a);n=64;vs=[]
 for z,rr in [(0,r),(d.length,r),(0,r-.009),(d.length,r-.009)]:
  for i in range(n):vs.append((rr*math.cos(i*2*math.pi/n),rr*math.sin(i*2*math.pi/n),z))
 fs=[]
 for i in range(n):
  j=(i+1)%n;fs.extend([(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),(i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)])
 o=mesh(name,vs,fs,mat);o.location=a;o.rotation_euler=d.to_track_quat('Z','Y').to_euler();return o
for x in [-.61,.61]:
 for y in [-.43,.43]:
  box('Square tube leg',(x,y,.43),(.065,.065,.84));box('Foot plate',(x,y,.025),(.14,.14,.025))
  for dx in [-.046,.046]:cyl('Anchor bolt',(x+dx,y,.045),.011,.018,bolt,verts=6)
for y in [-.43,.43]:box('Lower cross rail',(0,y,.25),(1.26,.05,.055))
for x in [-.61,.61]:
 box('Lower side rail',(x,0,.25),(.055,.9,.055));beam('Diagonal side brace',(x,-.4,.28),(x,.4,.8),.033)
box('Lower storage shelf',(0,0,.265),(1.18,.79,.023))
# Work surface uses four panels around a true open firepot.
box('Hearth left',(-.4425,0,.875),(.435,1.05,.045))
box('Hearth right',(.4425,0,.875),(.435,1.05,.045))
for y in [-.3725,.3725]:box('Hearth front/rear',(0,y,.875),(.45,.305,.045))
for y in [-.525,.525]:box('Riveted apron',(0,y,.817),(1.38,.038,.14),rust)
for x in [-.69,.69]:box('Side apron',(x,0,.817),(.038,1.05,.14),rust)
for x in [-.59,-.39,-.19,.19,.39,.59]:cyl('Apron rivet',(x,-.55,.817),.013,.012,bolt,(0,1,0),12)
C=collection('02 • Refractory hearth and hood')
# Sloping thick-walled firepot, open throat.
vs=[]
for z,w in [(.9,.225),(.70,.085)]:vs += [(-w,-w,z),(w,-w,z),(w,w,z),(-w,w,z)]
o=mesh('Cast iron tapered firepot',vs,[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],rust);o.modifiers.new('Casting thickness','SOLIDIFY').thickness=.022;o.modifiers.new('Casting radius','BEVEL').width=.008
for x in [-.065,-.0325,0,.0325,.065]:box('Tuyere grate',(x,0,.709),(.014,.16,.015),bolt,.002)
for row in range(4):
 for col in range(6):
  x=-.525+col*.21
  box('Back firebrick',(x,.445,.956+row*.116),(.202,.095,.108),brick,.006)
 for x in [-.592,.592]:
  for col in range(4):box('Side firebrick',(x,-.28+col*.203,.956+row*.116),(.095,.195,.108),brick,.006)
for x in [-.665,.665]:box('Steel cheek',(x,.075,1.145),(.025,.85,.49))
box('Back skin',(0,.51,1.145),(1.35,.025,.49))
for x in [-.67,.67]:box('Front corner strap',(x,-.36,1.155),(.065,.025,.54),rust)
# Tapered hood shell with open underside and flue mouth.
vs=[(-.72,-.48,1.43),(.72,-.48,1.43),(.72,.56,1.43),(-.72,.56,1.43),(-.18,.02,1.84),(.18,.02,1.84),(.18,.38,1.84),(-.18,.38,1.84)]
o=mesh('Tapered smoke hood',vs,[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],steel);o.modifiers.new('Sheet thickness','SOLIDIFY').thickness=.014;o.modifiers.new('Fold radius','BEVEL').width=.006
box('Hood front lip',(0,-.486,1.433),(1.47,.028,.065),rust)
pipe('Open chimney',(0,.20,1.81),(0,.20,2.45),.172)
for z in [1.87,2.35]:pipe('Chimney seam band',(0,.2,z-.025),(0,.2,z+.025),.185,rust)
for x in [-.65,.65]:
 for z in [1.0,1.23,1.39]:cyl('Cheek fastening',(x,-.383,z),.011,.012,bolt,(0,1,0),6)
C=collection('03 • Air feed and ash cleanout')
pipe('Vertical tuyere',(0,0,.44),(0,0,.70),.084)
cyl('Ash drop cap',(0,0,.44),.1,.022,rust)
beam('Cleanout lever',(0,-.03,.445),(.25,-.03,.445),.018,bolt)
cyl('Cleanout grip',(.25,-.03,.445),.022,.10,steel,(0,1,0))
pipe('Air feed',(0,0,.57),(.91,0,.57),.066)
for x in [.16,.75]:
 cyl('Air feed flange',(x,0,.57),.093,.018,rust,(1,0,0))
 for angle in [0,math.pi/2,math.pi,3*math.pi/2]:cyl('Flange bolt',(x+.013,.08*math.cos(angle),.57+.08*math.sin(angle)),.009,.018,bolt,(1,0,0),6)
box('Blower bracket',(.90,0,.32),(.35,.34,.034));beam('Blower support',(.62,0,.28),(.96,0,.32),.04)
cyl('Blower housing',(.99,0,.56),.175,.18,steel,(0,1,0));cyl('Intake surround',(.99,-.11,.56),.134,.03,rust,(0,1,0))
cyl('Intake shadow',(.99,-.13,.56),.118,.009,coal,(0,1,0))
for i in range(-4,5):
 z=i*.022;w=math.sqrt(.112**2-z*z)*2;box('Intake grille',(.99,-.141,.56+z),(w,.009,.008),bolt,.002)
cyl('Motor body',(.99,.19,.56),.095,.19,steel,(0,1,0))
beam('Damper stem',(.62,0,.57),(.62,0,.76),.015,bolt);box('Damper handle',(.62,-.04,.755),(.023,.13,.019),rust)
C=collection('04 • Fuel and workshop details')
ember=material('Ember orange',(.18,.025,.004),0,.9);p=ember.node_tree.nodes.get('Principled BSDF');p.inputs['Emission Color'].default_value=(1,.065,.002,1);p.inputs['Emission Strength'].default_value=3
for i in range(135):
 x=random.uniform(-.29,.29);y=random.uniform(-.29,.29)
 z=.89+max(0,1-math.hypot(x,y)/.34)*.075+random.uniform(-.015,.02)
 bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=random.uniform(.019,.043),location=(x,y,z));o=bpy.context.object;o.scale=(1,.85,.7);o.rotation_euler=(random.random(),random.random(),random.random());finish(o,'Coal / coke',ember if math.hypot(x,y)<.11 and random.random()<.45 else coal)
# Stock resting through the front opening.
bar=box('Workpiece',(0,-.31,1.01),(.027,.91,.027),bolt,.002)
box('Maker plate',(-.37,-.551,.814),(.30,.014,.074),steel,.005)
bpy.ops.object.text_add(location=(-.494,-.562,.795),rotation=(math.pi/2,0,0));o=bpy.context.object;o.data.body='COAL / 01';o.data.size=.039;o.data.extrude=.0006;finish(o,'Stamped maker label',bolt)
beam('Tool rail',(-.57,-.64,.71),(.57,-.64,.71),.022,bolt)
for x in [-.56,.56]:beam('Rail mount',(x,-.52,.71),(x,-.64,.71),.022)
for x in [.30,.38]:beam('Tongs handle',(x,-.64,.70),(x-.035,-.64,.36),.012,steel)
beam('Tongs joint',(.265,-.64,.36),(.345,-.64,.36),.012,bolt)
for x in [-.42,-.28,-.14]:box('Stock on shelf',(x,0,.31),(.025,.7,.026),rust,.002)
C=collection('05 • Studio presentation')
box('Concrete floor',(0,0,-.014),(200,200,.02),ground,.0)
def aim(o,p):o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(3.3,-4.7,3.0));c=finish(bpy.context.object,'Hero camera',None);aim(c,(.08,0,1.13));c.data.type='ORTHO';c.data.ortho_scale=3.35;s.camera=c
for name,pos,power,size,color in [('Key',(0,-3,4.5),650,3,(1,.83,.67)),('Cool rim',(2,2,3.7),850,2,(.60,.76,1)),('Fill',(-3,-1,2.6),420,2,(.85,.91,1))]:
 bpy.ops.object.light_add(type='AREA',location=pos);o=finish(bpy.context.object,name,None);o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.data.color=color;aim(o,(0,0,1))
bpy.ops.object.light_add(type='POINT',location=(0,0,1.06));o=finish(bpy.context.object,'Coal glow',None);o.data.energy=9;o.data.color=(1,.12,.015);o.data.shadow_soft_size=.12
s.world.color=(.17,.17,.17);s.render.engine='CYCLES';s.cycles.samples=48;s.cycles.use_denoising=True
s.render.resolution_x=1400;s.render.resolution_y=1400;s.render.resolution_percentage=100
s.unit_settings.system='METRIC';s.render.filepath='/path/to/project/forge/forge-redesign.png'
s['Design note']='Visual workshop forge concept; nominal 1.4m hearth width. Fabrication dimensions, draft and thermal performance are not validated. Original blockout is archived in hidden collection.'
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':
   area.spaces.active.region_3d.view_perspective='CAMERA'
bpy.ops.wm.save_as_mainfile(filepath='/path/to/project/forge/forge-redesign.blend');bpy.ops.render.render(write_still=True)
