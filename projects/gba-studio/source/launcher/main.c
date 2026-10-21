#include "raylib.h"
#include "player_settings.h"
#include <unistd.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>

#ifndef PROJECT_ROOT
#define PROJECT_ROOT "."
#endif
#ifndef PYTHON_PATH
#define PYTHON_PATH "python3"
#endif
#define MAX_GAMES 4096
static Color bg={246,248,251,255},panel={255,255,255,255},muted={110,119,137,255},ink={30,39,56,255},mint={62,101,225,255},edge={226,231,239,255},amber={156,104,30,255};
static Color tint={236,241,255,255},green={35,133,99,255};
static Font font,bold;
static char root[4096]=PROJECT_ROOT,state[4096],notice[256]="Drop .gb, .gbc, .gba files or a folder to get started.",logpath[4096];
static char model[512]="qwen3.8:27b-mlx",models[128][512];static int modelcount;
typedef struct {char sha[41],name[512],code[16],status[24];int size;char system[8];int units,queued;} Game;
static Game games[MAX_GAMES];static int count,selected,tab,scroll,capture=-1;static bool override,busy;static pid_t child=-1;
static PlayerSettings settings;
static void txt(const char *s,float x,float y,int size,Color c){DrawTextEx(size>=22?bold:font,s,(Vector2){x,y},size,0,c);}
static void box(float x,float y,float w,float h,Color c){DrawRectangleRounded((Rectangle){x,y,w,h},0.12f,12,c);}
static bool hit(float x,float y,float w,float h){return CheckCollisionPointRec(GetMousePosition(),(Rectangle){x,y,w,h});}
static bool button(const char *s,float x,float y,float w,bool active,bool enabled){
    Color c=active?mint:panel;
    if(enabled&&hit(x,y,w,42))c=active?(Color){49,83,196,255}:tint;
    if(!enabled)c=(Color){238,241,246,255};
    box(x,y,w,42,c);
    if(!active)DrawRectangleRoundedLinesEx((Rectangle){x,y,w,42},0.12f,12,1,edge);
    txt(s,x+16,y+12,16,enabled?(active?WHITE:ink):muted);
    return enabled&&capture<0&&hit(x,y,w,42)&&IsMouseButtonPressed(0);
}
static void path(char *out,size_t n,const char *leaf){snprintf(out,n,"%s/%s",state,leaf);}
static void configpath(char *out,size_t n){char leaf[80];snprintf(leaf,sizeof(leaf),"%s.cfg",override&&count?games[selected].sha:"global");path(out,n,leaf);}
static void load_settings(void){char p[4096];path(p,sizeof(p),"global.cfg");settings=player_defaults();player_load(&settings,p);override=false;if(count){snprintf(p,sizeof(p),"%s/%s.cfg",state,games[selected].sha);override=access(p,F_OK)==0;if(override)player_load(&settings,p);}}
static void save_settings(void){char p[4096];configpath(p,sizeof(p));snprintf(notice,sizeof(notice),"%s",player_save(&settings,p)?"Settings saved. Applied on the next C game launch.":"Could not save settings.");}
static void refresh(void){char p[4096],line[1800],old[41]="";if(count)snprintf(old,sizeof(old),"%s",games[selected].sha);path(p,sizeof(p),"library.tsv");FILE*f=fopen(p,"r");count=0;if(f){while(fgets(line,sizeof(line),f)&&count<MAX_GAMES){Game*g=&games[count];memset(g,0,sizeof(*g));snprintf(g->system,sizeof(g->system),"GBA");if(sscanf(line,"%40[^\t]\t%511[^\t]\t%15[^\t]\t%23[^\t]\t%d\t%7[^\t]\t%d\t%d",g->sha,g->name,g->code,g->status,&g->size,g->system,&g->units,&g->queued)>=5)count++;}fclose(f);}selected=0;for(int i=0;i<count;i++)if(!strcmp(old,games[i].sha))selected=i;
    path(p,sizeof(p),"model.txt");f=fopen(p,"r");if(f){if(fgets(model,sizeof(model),f))model[strcspn(model,"\r\n")]=0;fclose(f);}
    path(p,sizeof(p),"models.txt");f=fopen(p,"r");modelcount=0;if(f){while(modelcount<128&&fgets(models[modelcount],512,f)){models[modelcount][strcspn(models[modelcount],"\r\n")]=0;if(models[modelcount][0])modelcount++;}fclose(f);}load_settings();}
static void start_job_many(const char *action,int argc,char **args){
    if(busy)return;char backend[4096];snprintf(backend,sizeof(backend),"%s/launcher/backend.py",root);
    child=fork();if(child==0){setsid();int fd=open(logpath,O_WRONLY|O_CREAT|O_TRUNC,0644);if(fd>=0){dup2(fd,1);dup2(fd,2);close(fd);}char **av=calloc(argc+4,sizeof(char*));av[0]=PYTHON_PATH;av[1]=backend;av[2]=(char*)action;for(int i=0;i<argc;i++)av[i+3]=args[i];execv(PYTHON_PATH,av);perror("Start backend");_exit(127);}
    if(child<0){snprintf(notice,sizeof(notice),"Could not start task: %s",strerror(errno));return;}
    busy=true;snprintf(notice,sizeof(notice),"%s in progress. See Activity for output.",!strcmp(action,"play")?"Game":action);
}
static void start_job(const char *action,const char *arg){char *args[]={(char*)arg};start_job_many(action,arg?1:0,args);}
static void poll_job(void){if(!busy)return;int status;if(waitpid(child,&status,WNOHANG)==child){busy=false;refresh();snprintf(notice,sizeof(notice),"%s",WIFEXITED(status)&&WEXITSTATUS(status)==0?"Task finished. Library updated.":"Task failed. Open Activity for details.");}}
static const char *keyname(int k){switch(k){case 257:return "Enter";case 340:return "Left Shift";case 344:return "Right Shift";case 262:return "Right";case 263:return "Left";case 264:return "Down";case 265:return "Up";case 32:return "Space";case 258:return "Tab";default:if(k>=33&&k<=126)return TextFormat("%c",k);return TextFormat("Key %d",k);}}
static void card(float x,float y,float w,float h){
    float radius=16.0f/(w<h?w:h);
    DrawRectangleRounded((Rectangle){x,y+2,w,h},radius,12,(Color){235,239,245,255});
    DrawRectangleRounded((Rectangle){x,y,w,h},radius,12,panel);
    DrawRectangleRoundedLinesEx((Rectangle){x,y,w,h},radius,12,1,edge);
}
static void fittext(const char *s,float x,float y,int size,float width,Color color){
    char text[1024];snprintf(text,sizeof(text),"%s",s);Font f=size>=22?bold:font;
    int len=strlen(text);if(MeasureTextEx(f,text,size,0).x>width){
        while(len>0){text[--len]=0;if(MeasureTextEx(f,text,size,0).x<width-18)break;}
        strncat(text,"...",sizeof(text)-strlen(text)-1);
    }txt(text,x,y,size,color);
}
static void header(const char *title,const char *sub){txt(title,248,43,30,ink);txt(sub,248,88,16,muted);}
static void metric(float x,float y,float w,const char *label,int value,const char *detail){
    card(x,y,w,106);txt(label,x+20,y+16,14,muted);txt(TextFormat("%02d",value),x+20,y+44,30,ink);txt(detail,x+76,y+57,13,muted);
}
static const char *game_status(Game *g){
    if(!strcmp(g->status,"ready"))return "Native build ready";
    if(!strcmp(g->status,"build"))return "Native source available";
    if(!strcmp(g->status,"error"))return "Recovery needs attention";
    if(!strcmp(g->status,"recovering"))return "Recovery in progress";
    return g->units?"C drafts / review required":"Ready for C recovery";
}
static void scope(float w){
    txt("SETTINGS SCOPE",248,145,14,mint);
    if(button(override?"This game overrides":"Global defaults",248,171,228,false,count>0)){if(override){char p[4096];configpath(p,sizeof(p));if(unlink(p)&&errno!=ENOENT)snprintf(notice,sizeof(notice),"Could not remove override");load_settings();}else{override=true;save_settings();}} 
    txt(count?games[selected].name:"Import a game to add an override",500,183,18,muted);
    if(button("Save settings",w-216,171,172,true,true))save_settings();
}
static void library_view(float w,float h){
    header("Dashboard","Your ROM projects, source recovery and native builds.");
    if(button("Import folder",w-372,42,154,false,!busy))start_job("folder",NULL);
    if(button("+ Import ROM",w-204,42,164,true,!busy))start_job("pick",NULL);
    float cw=w-288,mw=(cw-32)/3;
    int ready=0,drafts=0;for(int i=0;i<count;i++){ready+=!strcmp(games[i].status,"ready");drafts+=games[i].units;}
    metric(248,132,mw,"PROJECTS",count,"in your library");
    metric(248+mw+16,132,mw,"NATIVE BUILDS",ready,"ready to launch");
    metric(248+2*(mw+16),132,mw,"C DRAFTS",drafts,"recovered blocks");
    float left=248,top=264,lw=(cw-20)*0.56f,right=left+lw+20,rw=cw-lw-20,ch=h-366;
    card(left,top,lw,ch);txt("Projects",left+22,top+21,22,ink);
    txt("GB / GBC / GBA",left+22,top+54,13,muted);
    DrawLine(left,top+91,left+lw,top+91,edge);
    int visible=(ch-108)/79;if(visible<1)visible=1;
    if(hit(left,top+93,lw,ch-96))scroll-=(int)GetMouseWheelMove();
    if(scroll>count-visible)scroll=count-visible;if(scroll<0)scroll=0;
    for(int i=scroll;i<count&&i<scroll+visible;i++){
        float y=top+103+(i-scroll)*79;
        if(i==selected)box(left+10,y-3,lw-20,71,tint);
        else if(hit(left+10,y-3,lw-20,71))box(left+10,y-3,lw-20,71,bg);
        box(left+23,y+9,42,42,i==selected?(Color){219,228,255,255}:bg);
        txt(games[i].system,left+29,y+23,12,i==selected?mint:muted);
        fittext(games[i].name,left+79,y+10,17,lw-108,ink);
        txt(game_status(&games[i]),left+79,y+37,13,!strcmp(games[i].status,"ready")?green:muted);
        if(!busy&&hit(left+10,y-3,lw-20,71)&&IsMouseButtonPressed(0)){selected=i;capture=-1;load_settings();}
    }
    if(!count){txt("No projects yet",left+24,top+139,22,ink);txt("Import a ROM or drop a folder here.",left+24,top+176,16,muted);}
    card(right,top,rw,ch);txt("SELECTED PROJECT",right+22,top+23,12,muted);
    bool supported=count&&!strcmp(games[selected].sha,"f3ae088181bf583e55daf962a92bb46f4f1d07b7");
    fittext(count?games[selected].name:"Start a project",right+22,top+53,23,rw-44,ink);
    txt(count?TextFormat("%s  /  %.1f MB",games[selected].system,games[selected].size/(1024.0f*1024.0f)):"GB, GBC and GBA supported",right+22,top+89,14,muted);
    DrawLine(right+22,top+122,right+rw-22,top+122,edge);
    const char *steps[]={"ROM imported","C source recovery","Native Mac build"};
    for(int i=0;i<3;i++){
        float y=top+148+i*56;bool done=count&&(i==0||(i==1&&supported)||(i==2&&supported&&!strcmp(games[selected].status,"ready")));
        DrawCircle(right+29,y+8,5,done?green:edge);
        txt(steps[i],right+46,y,15,ink);
        const char *sub=i==0?(count?"Original preserved":"Waiting for import"):i==1?(supported?"Existing recovered source":count?TextFormat("%d drafts / %d queued",games[selected].units,games[selected].queued):"Local model workflow"):(supported?"Available in Library":"Platform work and validation remain");
        fittext(sub,right+46,y+22,12,rw-66,muted);
    }
    float actions=top+ch-112;
    if(button(supported?"Launch native game":"Recover C / Resume",right+22,actions,rw-44,true,!busy&&count>0&&(!supported||!strcmp(games[selected].status,"ready")))){start_job(supported?"play":"recover",games[selected].sha);if(!supported)tab=4;}
    float half=(rw-56)/2;
    if(button(supported?"Rebuild":"C Recovery",right+22,actions+54,half,false,!busy&&count>0)){if(supported)start_job("build",games[selected].sha);else tab=3;}
    if(button("Open project",right+34+half,actions+54,half,false,!busy&&count>0))start_job("project",games[selected].sha);
    txt("All projects stay on this Mac.",248,h-77,13,muted);
}
static void display_view(float w){
    header("Display settings","Window and presentation preferences for native game builds.");scope(w);
    txt("WINDOW MODE",248,250,14,muted);
    if(button("Windowed",248,279,175,!settings.fullscreen,true)){settings.fullscreen=0;save_settings();}
    if(button("Fullscreen",435,279,175,settings.fullscreen,true)){settings.fullscreen=1;save_settings();}
    txt("WINDOW RESOLUTION",248,351,14,muted);
    const int rw[]={720,960,1280,1920},rh[]={480,640,720,1080};
    for(int i=0;i<4;i++)if(button(TextFormat("%d x %d",rw[i],rh[i]),248+i*190,380,178,settings.width==rw[i]&&settings.height==rh[i],true)){settings.width=rw[i];settings.height=rh[i];save_settings();}
    txt("SCALING",248,452,14,muted);const char*sc[]={"Fit aspect ratio","Stretch to fill","Integer pixels"};
    for(int i=0;i<3;i++)if(button(sc[i],248+i*240,481,228,settings.scale==i,true)){settings.scale=i;save_settings();}
    txt("Fit preserves the original shape. Stretch fills the window. Integer keeps whole pixels.",248,537,17,muted);
    txt("TEXTURE FILTER",248,594,14,muted);
    if(button("Crisp pixels",248,623,200,!settings.filter,true)){settings.filter=0;save_settings();}
    if(button("Smooth",460,623,200,settings.filter,true)){settings.filter=1;save_settings();}
    txt("Fullscreen follows your monitor resolution. F11 toggles it while playing.",248,692,17,muted);
}
static void controls_view(float w){
    header("Controls","Choose keyboard bindings for native game builds. Esc cancels a binding.");scope(w);
    for(int i=0;i<10;i++){float x=248+(i/5)*395,y=255+(i%5)*69;txt(player_actions[i],x,y+12,20,ink);
        if(button(capture==i?"Press a key...":keyname(settings.keys[i]),x+105,y,244,capture==i,true)){capture=i;while(GetKeyPressed());}}
    txt("CONTROLLER",248,624,14,mint);txt("Automatic: D-pad / left stick, A/B, shoulders, Start and Select.",248,652,18,ink);
    txt("Controller mapping uses Raylib defaults; custom remapping is keyboard-only.",248,681,16,muted);
    if(button("Reset bindings",w-244,624,200,false,true)){PlayerSettings d=player_defaults();memcpy(settings.keys,d.keys,sizeof(d.keys));save_settings();}
}
static void activity_view(float w,float h){
    header("Activity","Local model and compiler output. Recovery progress is saved per project.");
    if(button("Stop task",w-210,48,170,false,busy)){kill(-child,SIGTERM);snprintf(notice,sizeof(notice),"Stopping task. Saved blocks remain available for resume.");}
    box(248,140,w-286,h-226,panel);FILE*f=fopen(logpath,"r");char lines[32][512];int n=0;if(f){char buf[4096];while(fgets(buf,sizeof(buf),f)){snprintf(lines[n%32],512,"%.500s",buf);n++;}fclose(f);}
    int rows=(h-276)/21,start=n>rows?n-rows:0;if(start<n-32)start=n-32;
    BeginScissorMode(266,156,w-324,h-263);for(int i=start;i<n;i++){char *s=lines[i%32];s[strcspn(s,"\r\n")]=0;txt(s,266,158+(i-start)*21,15,muted);}EndScissorMode();
}
static void recovery_view(float w){
    header("C Recovery","Recover editable source with a local model, then review and build.");
    card(248,133,w-288,124);txt("SELECTED PROJECT",270,151,12,muted);
    fittext(count?games[selected].name:"Select a project in Dashboard",270,177,24,w-342,ink);
    txt(count?TextFormat("%s  /  %d C drafts  /  %d queued blocks",games[selected].system,games[selected].units,games[selected].queued):"Import a GB, GBC or GBA cartridge to begin.",270,218,15,muted);
    card(248,279,w-288,170);txt("LOCAL MODEL",270,300,12,muted);
    fittext(model,270,330,20,w-342,ink);
    if(button("Refresh models",270,385,168,false,!busy))start_job("models",NULL);
    if(button("Next local model",450,385,183,false,!busy&&modelcount>0)){int index=-1;for(int i=0;i<modelcount;i++)if(!strcmp(model,models[i]))index=i;start_job("model",models[(index+1)%modelcount]);}
    txt("Runs on this Mac",w-195,399,13,green);
    if(button("Recover C / Resume",248,473,220,true,!busy&&count>0)){start_job("recover",games[selected].sha);tab=4;}
    if(button("Compile drafts",480,473,185,false,!busy&&count>0)){start_job("compile",games[selected].sha);tab=4;}
    if(button("Open project",677,473,160,false,!busy&&count>0))start_job("project",games[selected].sha);
    bool supported=count&&!strcmp(games[selected].sha,"f3ae088181bf583e55daf962a92bb46f4f1d07b7");
    box(248,546,w-288,100,tint);txt(supported?"Native source available":"Recovery is a work in progress",270,565,18,ink);
    txt(supported?"Emerald has an existing native C port. Launch it from Dashboard.":"C drafts need behavior checks and platform services before they become a native game.",270,597,15,muted);
    if(button("Choose emulator",248,669,184,false,!busy))start_job("emulator",NULL);
    if(button("Open ROM externally",444,669,205,false,!busy&&count>0))start_job("fallback",games[selected].sha);
    txt("Optional external tool",667,683,13,muted);
}
int main(void){
    snprintf(state,sizeof(state),"%s/workspace/launcher",root);snprintf(logpath,sizeof(logpath),"%s/activity.log",state);
    SetConfigFlags(FLAG_WINDOW_RESIZABLE|FLAG_VSYNC_HINT|FLAG_WINDOW_HIGHDPI);InitWindow(1240,820,"GBA Studio");SetWindowMinSize(1160,780);SetExitKey(KEY_NULL);SetTargetFPS(60);
    font=LoadFontEx("/System/Library/Fonts/Supplemental/Arial.ttf",40,NULL,0);if(font.texture.id==0)font=GetFontDefault();
    bold=LoadFontEx("/System/Library/Fonts/Supplemental/Arial Bold.ttf",48,NULL,0);if(bold.texture.id==0)bold=font;
    SetTextureFilter(font.texture,TEXTURE_FILTER_BILINEAR);SetTextureFilter(bold.texture,TEXTURE_FILTER_BILINEAR);refresh();start_job("refresh",NULL);
    while(!WindowShouldClose()){
        poll_job();
        if(capture<0){int ch;while((ch=GetCharPressed())>0)if(ch>='1'&&ch<='5')tab=ch-'1';}
        if(capture>=0){int k=GetKeyPressed();if(k==KEY_ESCAPE)capture=-1;else if(k>=32&&k<=348&&k!=KEY_F11){int old=settings.keys[capture];for(int i=0;i<10;i++)if(i!=capture&&settings.keys[i]==k)settings.keys[i]=old;settings.keys[capture]=k;capture=-1;save_settings();}}
        if(IsFileDropped()){FilePathList files=LoadDroppedFiles();if(!busy&&files.count){start_job_many("import",files.count,files.paths);}UnloadDroppedFiles(files);}
        float w=GetScreenWidth(),h=GetScreenHeight();BeginDrawing();ClearBackground(bg);DrawRectangle(0,0,210,h,panel);DrawLine(209,0,209,h,edge);
        box(24,35,32,32,mint);txt("S",34,41,20,WHITE);txt("GBA Studio",68,41,21,ink);
        txt("WORKSPACE",26,125,11,muted);const char*nav[]={"Dashboard","Display settings","Controls","C Recovery","Activity"};
        for(int i=0;i<5;i++){
            float y=157+i*52;bool active=tab==i;
            if(active)box(16,y,178,42,tint);else if(hit(16,y,178,42))box(16,y,178,42,bg);
            if(active)DrawRectangle(16,y+10,3,22,mint);
            txt(nav[i],32,y+13,16,active?mint:muted);
            if(capture<0&&hit(16,y,178,42)&&IsMouseButtonPressed(0)){tab=i;capture=-1;}
        }
        DrawLine(24,h-128,186,h-128,edge);DrawCircle(30,h-102,3,green);txt("Local workspace",42,h-111,13,ink);
        txt("GB / GBC / GBA",26,h-80,12,muted);txt("Studio 0.2",26,h-57,12,muted);
        if(tab==0)library_view(w,h);if(tab==1)display_view(w);if(tab==2)controls_view(w);if(tab==3)recovery_view(w);if(tab==4)activity_view(w,h);
        DrawLine(234,h-51,w-26,h-51,edge);DrawCircle(251,h-26,4,busy?amber:mint);fittext(notice,265,h-35,14,w-304,muted);
        EndDrawing();
    }CloseWindow();return 0;
}
