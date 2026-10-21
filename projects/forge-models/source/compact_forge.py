import bpy, math, random
from mathutils import Vector
random.seed(32)
bpy.ops.wm.read_factory_settings(use_empty=True)
s=bpy.context.scene
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
# 550 mm envelope: compact cubic tabletop concept.
for m in [steel,rust,bolt,brick,coal]:
 b=m.node_tree.nodes.get('Bump');b.inputs['Distance'].default_value=.0012;b.inputs['Strength'].default_value=.16
steel.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.57
C.name='01 • Cubic shell'
box('Base plate',(0,0,.018),(.55,.55,.016),steel,.003)
for x in [-.23,.23]:
 for y in [-.23,.23]:box('Low foot',(x,y,.005),(.052,.052,.01),coal,.003)
for x in [-.263,.263]:
 for y in [-.263,.263]:box('Corner post',(x,y,.287),(.024,.024,.524),steel,.003)
box('Rear shell',(0,.270,.28),(.502,.01,.508),steel,.002)
for x in [-.270,.270]:box('Upper side shell',(x,0,.388),(.01,.502,.294),steel,.002)
# Roof with a flush square exhaust opening toward the back.
box('Roof front',(0,-.115,.544),(.55,.32,.012),steel,.003)
box('Roof back',(0,.245,.544),(.55,.06,.012),steel,.003)
for x in [-.18,.18]:box('Roof side',(x,.13,.544),(.19,.17,.012),steel,.003)
for x in [-.09,.09]:box('Exhaust socket side',(x,.13,.520),(.009,.18,.036),bolt,.001)
for y in [.04,.22]:box('Exhaust socket end',(0,y,.520),(.18,.009,.036),bolt,.001)
box('Upper front fascia',(0,-.269,.502),(.502,.012,.071),steel,.003)
box('Upper lip accent',(0,-.273,.463),(.498,.004,.008),rust,.001)
# Enclosed lower service bay, inset vents and accessible ash drawer.
box('Front service face',(0,-.265,.115),(.502,.012,.168),steel,.003)
box('Ash drawer seam',(-.073,-.272,.12),(.30,.002,.103),coal,.002)
box('Ash drawer front',(-.073,-.274,.12),(.287,.002,.090),steel,.003)
box('Recessed pull shadow',(-.073,-.275,.126),(.085,.001,.019),coal,.002)
box('Recessed pull edge',(-.073,-.275,.132),(.073,.001,.004),bolt,.001)
cyl('Air control knob',(.171,-.266,.128),.018,.016,bolt,(0,1,0))
box('Knob indicator',(.171,-.275,.136),(.002,.001,.01),rust,.0004)
for x in [-.27,.27]:
 box('Service side upper',(x,0,.207),(.01,.502,.028),steel,.002)
 box('Service side lower',(x,0,.049),(.01,.502,.04),steel,.002)
 for y in [-.207,.207]:box('Side vent surround',(x,y,.127),(.01,.09,.116),steel,.002)
 for i in range(7):box('Vent louvre',(x,-.001,.075+i*.017),(.008,.31,.011),steel,.0015)
# Hearth tray split around an actual recessed pot.
C=collection('02 • Hearth and firebrick')
for x in [-.173,.173]:box('Hearth side',(x,0,.237),(.19,.5,.02),steel,.002)
for y in [-.173,.173]:box('Hearth end',(0,y,.237),(.156,.19,.02),steel,.002)
box('Front hearth rail',(0,-.270,.234),(.55,.01,.023),rust,.002)
vs=[]
for z,w in [(.247,.078),(.184,.031)]:vs += [(-w,-w,z),(w,-w,z),(w,w,z),(-w,w,z)]
o=mesh('Recessed firepot',vs,[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],rust);o.modifiers.new('Cast wall','SOLIDIFY').thickness=.005
for x in [-.021,-.007,.007,.021]:box('Grate bar',(x,0,.187),(.006,.061,.008),bolt,.001)
for row in range(3):
 for col in range(4):box('Rear firebrick',(-.174+col*.116,.235,.28+row*.062),(.112,.04,.058),brick,.0018)
 for x in [-.235,.235]:
  for col in range(4):box('Side firebrick',(x,-.174+col*.116,.28+row*.062),(.04,.112,.058),brick,.0018)
C=collection('03 • Internal air and ash system')
pipe('Tuyere',(0,0,.10),(0,0,.182),.030)
pipe('Air duct',(0,0,.135),(.165,0,.135),.025)
cyl('Compact blower',(.163,.063,.128),.063,.073,steel,(0,1,0))
cyl('Blower intake',(.163,.108,.128),.044,.016,coal,(0,1,0))
cyl('Ash cup',(0,0,.085),.039,.033,rust)
box('Ash tray',(-.07,-.04,.057),(.26,.37,.025),rust,.003)
C=collection('04 • Coal and details')
ember=material('Embers',(.11,.018,.003),0,.8);p=ember.node_tree.nodes.get('Principled BSDF');p.inputs['Emission Color'].default_value=(1,.065,.002,1);p.inputs['Emission Strength'].default_value=2.5
for i in range(90):
 x=random.uniform(-.11,.11);y=random.uniform(-.10,.10);z=.247+max(0,1-math.hypot(x,y)/.13)*.027
 bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=random.uniform(.008,.015),location=(x,y,z));o=bpy.context.object;o.scale=(1,.85,.7);o.rotation_euler=(random.random(),random.random(),random.random());finish(o,'Coal',ember if math.hypot(x,y)<.043 and random.random()<.50 else coal)
for x in [-.251,.251]:
 for z in [.045,.216,.483,.525]:cyl('Flush hardware',(x,-.269,z),.0035,.008,bolt,(0,1,0),6)
bpy.ops.object.text_add(location=(-.224,-.276,.493),rotation=(math.pi/2,0,0));o=bpy.context.object;o.data.body='C O A L  /  5 5';o.data.size=.014;o.data.extrude=.0001;finish(o,'Front mark',bolt)
# Verify the physical assembly envelope before adding the studio.
bpy.context.view_layer.update()
coords=[o.matrix_world@Vector(v) for o in s.objects if o.type=='MESH' for v in o.bound_box]
dims=[max(v[i] for v in coords)-min(v[i] for v in coords) for i in range(3)]
print('COMPACT ENVELOPE METRES',dims)
C=collection('05 • Presentation')
box('Studio floor',(0,0,-.008),(200,200,.016),ground,0)
def aim(o,p):o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(.94,-1.40,.94));c=finish(bpy.context.object,'Compact hero',None);aim(c,(0,0,.27));c.data.type='ORTHO';c.data.ortho_scale=.92;s.camera=c
for name,pos,power,size,color in [('Warm key',(-.6,-.9,1.4),95,.9,(1,.86,.72)),('Cool rim',(.8,.5,1.2),135,.7,(.67,.81,1)),('Soft fill',(-.8,.1,.5),45,.8,(.88,.94,1))]:
 bpy.ops.object.light_add(type='AREA',location=pos);o=finish(bpy.context.object,name,None);o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.data.color=color;aim(o,(0,0,.27))
bpy.ops.object.light_add(type='POINT',location=(0,-.02,.30));o=finish(bpy.context.object,'Ember glow',None);o.data.energy=.7;o.data.color=(1,.12,.018);o.data.shadow_soft_size=.04
s.world=bpy.data.worlds.new('Studio world');s.world.use_nodes=True;s.world.node_tree.nodes['Background'].inputs[0].default_value=(.12,.15,.20,1);s.world.node_tree.nodes['Background'].inputs[1].default_value=.3
s.render.engine='CYCLES';s.cycles.samples=64;s.cycles.use_denoising=True;s.render.resolution_x=1500;s.render.resolution_y=1500;s.render.resolution_percentage=100;s.unit_settings.system='METRIC';s.unit_settings.length_unit='CENTIMETERS'
s['Concept']='COAL / 55 — compact cubic tabletop forge';s['Envelope']='55 × 55 × 55 cm';s['Systems']='Recessed hearth, brick enclosure, flush square exhaust socket, internal blower, ash drawer.'
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA'
s.render.filepath='/path/to/project/forge/forge-compact-55.png'
bpy.ops.wm.save_as_mainfile(filepath='/path/to/project/forge/forge-compact-55.blend');bpy.ops.render.render(write_still=True)
