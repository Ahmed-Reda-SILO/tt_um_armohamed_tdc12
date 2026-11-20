/* Read actual simulator path delays after SDF annotation. Verification only. */
#include <stdio.h>
#include <string.h>
#include "vpi_user.h"
static FILE *out;
static void visit(vpiHandle module) {
    vpiHandle it=vpi_iterate(vpiModPath,module),path;
    while(it && (path=vpi_scan(it))) {
        s_vpi_time values[12]; s_vpi_delay d;
        memset(values,0,sizeof values);memset(&d,0,sizeof d);
        d.da=values;d.no_of_delays=2;d.time_type=vpiScaledRealTime;
        vpi_get_delays(path,&d);
        const char *module_name=vpi_get_str(vpiFullName,module);
        char mod[512];snprintf(mod,sizeof mod,"%s",module_name?module_name:"");
        vpiHandle tin=vpi_handle(vpiModPathIn,path),tout=vpi_handle(vpiModPathOut,path);
        vpiHandle ein=tin?vpi_handle(vpiExpr,tin):0,eout=tout?vpi_handle(vpiExpr,tout):0;
        char src[128],dst[128];
        const char *s=ein?vpi_get_str(vpiName,ein):0;snprintf(src,sizeof src,"%s",s?s:"");
        s=eout?vpi_get_str(vpiName,eout):0;snprintf(dst,sizeof dst,"%s",s?s:"");
        fprintf(out,"%s,%s,%s,%.9f,%.9f\n",mod,src,dst,values[0].real,values[1].real);
    }
    it=vpi_iterate(vpiModule,module);
    vpiHandle child;
    while(it && (child=vpi_scan(it)))visit(child);
}
static PLI_INT32 finish(p_cb_data cb) {
    (void)cb;out=fopen("annotation_paths.csv","w");
    if(!out)return 0;
    fprintf(out,"instance,source_pin,destination_pin,rise_ns,fall_ns\n");
    vpiHandle top=vpi_handle_by_name("sine_wave_tb.dut",0);
    if(top)visit(top);fclose(out);return 0;
}
static void register_probe(void) {
    s_cb_data cb;memset(&cb,0,sizeof cb);cb.reason=cbEndOfSimulation;cb.cb_rtn=finish;vpi_register_cb(&cb);
}
void (*vlog_startup_routines[])(void)={register_probe,0};
