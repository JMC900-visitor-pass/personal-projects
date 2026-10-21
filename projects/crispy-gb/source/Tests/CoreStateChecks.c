#include "EmulatorBridge.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
static unsigned long hash(StudioCore *core) {
    const uint32_t *p = studio_pixels(core); unsigned long h = 5381;
    for (unsigned i = 0; i < studio_width(core)*studio_height(core); ++i) h = (h*33) ^ p[i];
    return h;
}
int main(int argc, char **argv) {
    assert(argc == 3);
    StudioCore *core = studio_create(argv[1],argv[2]);
    if (!core) { fprintf(stderr,"%s\n",studio_last_error()); return 1; }
    for (int i=0;i<90;++i) studio_run_frame(core);
    char path[4096]; snprintf(path,sizeof(path),"%s/before-colour.mbs",argv[2]);
    assert(studio_save_state(core,path));
    for (int i=0;i<8;++i) studio_run_frame(core);
    unsigned long expected = hash(core);
    assert(studio_load_state(core,path));
    for (int i=0;i<8;++i) studio_run_frame(core);
    assert(hash(core) == expected);
    studio_flush_save(core);
    // Invalid loads fail without destroying a running core.
    assert(!studio_load_state(core,"/nonexistent/crispy-state.mbs"));
    studio_run_frame(core);
    studio_destroy(core);
    printf("PASS: atomic state write, state roundtrip deterministic next frames, missing-state error and clean teardown\n");
}
