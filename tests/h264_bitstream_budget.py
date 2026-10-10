"""Compile actual InitBsBuffer/CheckBsBuffer with real OpenH264 types/allocator."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
c=root/'firmware/esp_mosaico/components/oft_openh264'
out=root/'artifacts/mosaico/h264-bitstream-contract'
out.mkdir(parents=True,exist_ok=True)
cmake=out/'generate.cmake'
cmake.write_text(f'cmake_minimum_required(VERSION 3.16)\nset(CMAKE_CURRENT_SOURCE_DIR "{c}")\nset(CMAKE_CURRENT_BINARY_DIR "{out}")\ninclude("{c}/compat/profile_sources.cmake")\n')
subprocess.run(['cmake','-P',str(cmake)],check=True)
original=(c/'vendor/codec/decoder/core/src/decoder_core.cpp').read_text()
generated=out/'profile_decoder_core.cpp'
text=generated.read_text()
marker='pCtx->iMaxBsBufferSizeInByte = MIN_ACCESS_UNIT_CAPACITY * MAX_BUFFERED_NUM;'
assert original.count(marker)==1
expected='#include "oft_profile.h"\n#include "oft_decode_limits.h"\n'+original.replace(marker,'pCtx->iMaxBsBufferSizeInByte = OFT_H264_INPUT_CAPACITY * MAX_BUFFERED_NUM;')
assert text==expected, 'Unexpected decoder source change'
def function(src,name):
    start=src.index('int32_t '+name+' (')
    brace=src.index('{',start);level=1;end=brace+1
    while level:
        level+=(src[end]=='{')-(src[end]=='}');end+=1
    return src[start:end]
assert function(text,'ExpandBsBuffer')==function(original,'ExpandBsBuffer'), 'Growth path changed'
assert function(text,'CheckBsBuffer')==function(original,'CheckBsBuffer'), 'Bounds check changed'
source=out/'contract.cpp'
source.write_text('''#include <cstdio>
#include <cstring>
#include "decoder_core.h"
#include "memory_align.h"
#include "oft_decode_limits.h"
#define WelsLog(...) ((void)0)
namespace WelsDec {
static int expands, requested;
int32_t ExpandBsBuffer(PWelsDecoderContext, const int n) { ++expands; requested=n; return 0; }
'''+function(text,'InitBsBuffer')+'\n'+function(text,'CheckBsBuffer')+'''
}
#define CHECK(x) do { if(!(x)){std::fprintf(stderr,"line %d: %s\\n",__LINE__,#x);return 1;} } while(0)
int main(){
 using namespace WelsDec;
 static SWelsDecoderContext ctx{};SDecodingParam param{};
 WelsCommon::CMemoryAlign allocator(16);ctx.pMemAlign=&allocator;ctx.pParam=&param;
 CHECK(InitBsBuffer(nullptr)==ERR_INFO_INVALID_PTR);
 CHECK(InitBsBuffer(&ctx)==0);
 CHECK(ctx.iMaxBsBufferSizeInByte==3*256*1024);
 CHECK(ctx.sRawData.pEnd-ctx.sRawData.pHead==ctx.iMaxBsBufferSizeInByte);
 CHECK(ctx.sRawData.pStartPos==ctx.sRawData.pHead && ctx.sRawData.pCurPos==ctx.sRawData.pHead);
 CHECK(CheckBsBuffer(&ctx,256*1024-64)==0 && expands==0);
 CHECK(CheckBsBuffer(&ctx,256*1024)==0 && expands==0);
 CHECK(CheckBsBuffer(&ctx,256*1024+1)==0 && expands==1 && requested==256*1024+1);
 CHECK(CheckBsBuffer(&ctx,MAX_ACCESS_UNIT_CAPACITY+1)==ERR_INFO_INVALID_ACCESS && expands==1);
 allocator.WelsFree(ctx.sRawData.pHead,"test");
 std::puts("H264 initial budget and unchanged growth boundary passed");
}
''')
include=[c/'compat',c/'vendor/codec/common/inc',c/'vendor/codec/decoder/core/inc',c/'vendor/codec/api/wels']
exe=out/'contract'
subprocess.run(['g++','-std=c++11','-O1','-DNDEBUG',*[f'-I{p}' for p in include],str(source),str(c/'vendor/codec/common/src/memory_align.cpp'),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True)
