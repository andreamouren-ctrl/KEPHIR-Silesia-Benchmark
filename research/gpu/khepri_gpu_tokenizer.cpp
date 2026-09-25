#include <CL/cl.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static const std::vector<std::string> TOKENS = {
    " the "," and ","ing","tion"," of "," to "," in "," that ",
    " is "," for ","ed ","er ","re ","en ","on ","at ",
    "\\n","</","/>","http","www.","=\"","<!--","-->",
    "data","this","with","from","have","not "," as "," by "
};

struct MatchResult {
    std::vector<uint8_t> id;
    std::vector<uint8_t> len;
    bool gpu_used = false;
    std::string device_name = "CPU fallback";
    double match_ms = 0.0;
};

static std::vector<uint8_t> read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open input");
    f.seekg(0, std::ios::end);
    const auto n = static_cast<size_t>(f.tellg());
    f.seekg(0);
    std::vector<uint8_t> v(n);
    if (n) f.read(reinterpret_cast<char*>(v.data()), static_cast<std::streamsize>(n));
    return v;
}

static void write_file(const std::string& path, const std::vector<uint8_t>& v) {
    std::ofstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open output");
    if (!v.empty()) f.write(reinterpret_cast<const char*>(v.data()), static_cast<std::streamsize>(v.size()));
}

static std::vector<size_t> token_order() {
    std::vector<size_t> order(TOKENS.size());
    for (size_t i=0;i<order.size();++i) order[i]=i;
    std::stable_sort(order.begin(), order.end(), [](size_t a,size_t b){
        return TOKENS[a].size() > TOKENS[b].size();
    });
    return order;
}

static MatchResult cpu_match(const std::vector<uint8_t>& in) {
    auto t0 = std::chrono::steady_clock::now();
    MatchResult r;
    r.id.assign(in.size(),0);
    r.len.assign(in.size(),0);
    const auto order=token_order();
    for (size_t i=0;i<in.size();++i) {
        for (size_t oi:order) {
            const auto& tok=TOKENS[oi];
            if (i+tok.size()>in.size()) continue;
            bool ok=true;
            for (size_t j=0;j<tok.size();++j) {
                if (in[i+j] != static_cast<uint8_t>(tok[j])) { ok=false; break; }
            }
            if (ok) {
                r.id[i]=static_cast<uint8_t>(oi+1);
                r.len[i]=static_cast<uint8_t>(tok.size());
                break;
            }
        }
    }
    auto t1=std::chrono::steady_clock::now();
    r.match_ms=std::chrono::duration<double,std::milli>(t1-t0).count();
    return r;
}

static std::vector<uint8_t> compact_tokens(const std::vector<uint8_t>& in,const MatchResult& m) {
    std::vector<uint8_t> out;
    out.reserve(in.size());
    for (size_t i=0;i<in.size();) {
        if (m.id[i] && m.len[i]) {
            out.push_back(255);
            out.push_back(m.id[i]);
            i += m.len[i];
        } else {
            const uint8_t b=in[i++];
            if (b==255) { out.push_back(255); out.push_back(0); }
            else out.push_back(b);
        }
    }
    return out;
}

static std::vector<uint8_t> detokenize(const std::vector<uint8_t>& in) {
    std::vector<uint8_t> out;
    for (size_t i=0;i<in.size();) {
        uint8_t b=in[i++];
        if (b!=255) { out.push_back(b); continue; }
        if (i>=in.size()) throw std::runtime_error("truncated token stream");
        uint8_t id=in[i++];
        if (id==0) out.push_back(255);
        else if (id>=1 && id<=TOKENS.size()) {
            const auto& t=TOKENS[id-1];
            out.insert(out.end(),t.begin(),t.end());
        } else throw std::runtime_error("bad token id");
    }
    return out;
}

static const char* KERNEL_SRC = R"CLC(
__kernel void token_match(
    __global const uchar* in, const uint n,
    __global const uchar* tok_bytes,
    __global const uint* tok_off,
    __global const uchar* tok_len,
    __global const uchar* tok_id,
    const uint ntok,
    __global uchar* best_id,
    __global uchar* best_len)
{
    const uint i=get_global_id(0);
    if (i>=n) return;
    best_id[i]=0;
    best_len[i]=0;
    for (uint k=0;k<ntok;++k) {
        const uchar L=tok_len[k];
        if (i+(uint)L>n) continue;
        const uint off=tok_off[k];
        int ok=1;
        for (uint j=0;j<(uint)L;++j) {
            if (in[i+j]!=tok_bytes[off+j]) { ok=0; break; }
        }
        if (ok) {
            best_id[i]=tok_id[k];
            best_len[i]=L;
            return;
        }
    }
}
)CLC";

static MatchResult gpu_match(const std::vector<uint8_t>& in) {
    MatchResult fallback;
    cl_int err=CL_SUCCESS;
    cl_uint np=0;
    if (clGetPlatformIDs(0,nullptr,&np)!=CL_SUCCESS || np==0) return cpu_match(in);
    std::vector<cl_platform_id> plats(np);
    clGetPlatformIDs(np,plats.data(),nullptr);

    cl_device_id dev=nullptr;
    for (auto p:plats) {
        cl_uint nd=0;
        if (clGetDeviceIDs(p,CL_DEVICE_TYPE_GPU,0,nullptr,&nd)==CL_SUCCESS && nd) {
            std::vector<cl_device_id> ds(nd);
            clGetDeviceIDs(p,CL_DEVICE_TYPE_GPU,nd,ds.data(),nullptr);
            dev=ds[0];
            break;
        }
    }
    if (!dev) return cpu_match(in);

    char name[256]={0};
    clGetDeviceInfo(dev,CL_DEVICE_NAME,sizeof(name),name,nullptr);

    cl_context ctx=clCreateContext(nullptr,1,&dev,nullptr,nullptr,&err);
    if (!ctx || err!=CL_SUCCESS) return cpu_match(in);
    cl_command_queue q=clCreateCommandQueue(ctx,dev,0,&err);
    if (!q || err!=CL_SUCCESS) { clReleaseContext(ctx); return cpu_match(in); }

    const char* src=KERNEL_SRC;
    const size_t slen=std::char_traits<char>::length(src);
    cl_program prog=clCreateProgramWithSource(ctx,1,&src,&slen,&err);
    if (!prog || err!=CL_SUCCESS) { clReleaseCommandQueue(q); clReleaseContext(ctx); return cpu_match(in); }
    err=clBuildProgram(prog,1,&dev,nullptr,nullptr,nullptr);
    if (err!=CL_SUCCESS) {
        size_t logn=0; clGetProgramBuildInfo(prog,dev,CL_PROGRAM_BUILD_LOG,0,nullptr,&logn);
        std::string log(logn,'\0');
        if (logn) clGetProgramBuildInfo(prog,dev,CL_PROGRAM_BUILD_LOG,logn,log.data(),nullptr);
        std::cerr<<"OpenCL build failed: "<<log<<"\n";
        clReleaseProgram(prog); clReleaseCommandQueue(q); clReleaseContext(ctx);
        return cpu_match(in);
    }
    cl_kernel kernel=clCreateKernel(prog,"token_match",&err);
    if (!kernel || err!=CL_SUCCESS) {
        clReleaseProgram(prog); clReleaseCommandQueue(q); clReleaseContext(ctx);
        return cpu_match(in);
    }

    auto order=token_order();
    std::vector<uint8_t> tokbytes,toklen,tokid;
    std::vector<uint32_t> tokoff;
    for (size_t oi:order) {
        tokoff.push_back(static_cast<uint32_t>(tokbytes.size()));
        toklen.push_back(static_cast<uint8_t>(TOKENS[oi].size()));
        tokid.push_back(static_cast<uint8_t>(oi+1));
        tokbytes.insert(tokbytes.end(),TOKENS[oi].begin(),TOKENS[oi].end());
    }

    auto mk=[&](cl_mem_flags flags,size_t bytes,const void* ptr)->cl_mem {
        cl_int e=CL_SUCCESS;
        cl_mem m=clCreateBuffer(ctx,flags,bytes,const_cast<void*>(ptr),&e);
        if (e!=CL_SUCCESS) throw std::runtime_error("clCreateBuffer failed");
        return m;
    };

    MatchResult r;
    r.id.assign(in.size(),0); r.len.assign(in.size(),0);
    r.gpu_used=true; r.device_name=name;
    cl_mem bin=nullptr,bbytes=nullptr,boff=nullptr,blen=nullptr,bid=nullptr,boutid=nullptr,boutlen=nullptr;
    try {
        const size_t nbytes=std::max<size_t>(1,in.size());
        bin=mk(CL_MEM_READ_ONLY|CL_MEM_COPY_HOST_PTR,nbytes,in.empty()?nullptr:in.data());
        bbytes=mk(CL_MEM_READ_ONLY|CL_MEM_COPY_HOST_PTR,tokbytes.size(),tokbytes.data());
        boff=mk(CL_MEM_READ_ONLY|CL_MEM_COPY_HOST_PTR,tokoff.size()*sizeof(uint32_t),tokoff.data());
        blen=mk(CL_MEM_READ_ONLY|CL_MEM_COPY_HOST_PTR,toklen.size(),toklen.data());
        bid=mk(CL_MEM_READ_ONLY|CL_MEM_COPY_HOST_PTR,tokid.size(),tokid.data());
        boutid=mk(CL_MEM_WRITE_ONLY,nbytes,nullptr);
        boutlen=mk(CL_MEM_WRITE_ONLY,nbytes,nullptr);
        const cl_uint n=static_cast<cl_uint>(in.size());
        const cl_uint nt=static_cast<cl_uint>(tokid.size());
        clSetKernelArg(kernel,0,sizeof(bin),&bin);
        clSetKernelArg(kernel,1,sizeof(n),&n);
        clSetKernelArg(kernel,2,sizeof(bbytes),&bbytes);
        clSetKernelArg(kernel,3,sizeof(boff),&boff);
        clSetKernelArg(kernel,4,sizeof(blen),&blen);
        clSetKernelArg(kernel,5,sizeof(bid),&bid);
        clSetKernelArg(kernel,6,sizeof(nt),&nt);
        clSetKernelArg(kernel,7,sizeof(boutid),&boutid);
        clSetKernelArg(kernel,8,sizeof(boutlen),&boutlen);
        auto t0=std::chrono::steady_clock::now();
        if (!in.empty()) {
            size_t global=((in.size()+255)/256)*256;
            err=clEnqueueNDRangeKernel(q,kernel,1,nullptr,&global,nullptr,0,nullptr,nullptr);
            if (err!=CL_SUCCESS) throw std::runtime_error("kernel enqueue failed");
            clFinish(q);
            clEnqueueReadBuffer(q,boutid,CL_TRUE,0,in.size(),r.id.data(),0,nullptr,nullptr);
            clEnqueueReadBuffer(q,boutlen,CL_TRUE,0,in.size(),r.len.data(),0,nullptr,nullptr);
        }
        auto t1=std::chrono::steady_clock::now();
        r.match_ms=std::chrono::duration<double,std::milli>(t1-t0).count();
    } catch (...) {
        if(bin)clReleaseMemObject(bin); if(bbytes)clReleaseMemObject(bbytes); if(boff)clReleaseMemObject(boff);
        if(blen)clReleaseMemObject(blen); if(bid)clReleaseMemObject(bid); if(boutid)clReleaseMemObject(boutid);
        if(boutlen)clReleaseMemObject(boutlen); clReleaseKernel(kernel); clReleaseProgram(prog);
        clReleaseCommandQueue(q); clReleaseContext(ctx);
        return cpu_match(in);
    }

    clReleaseMemObject(bin); clReleaseMemObject(bbytes); clReleaseMemObject(boff);
    clReleaseMemObject(blen); clReleaseMemObject(bid); clReleaseMemObject(boutid); clReleaseMemObject(boutlen);
    clReleaseKernel(kernel); clReleaseProgram(prog); clReleaseCommandQueue(q); clReleaseContext(ctx);
    return r;
}

int main(int argc,char** argv) {
    try {
        if (argc==2 && std::string(argv[1])=="--self-test") {
            std::string sample="the quick brown fox and the data with http://www.example.com\n";
            sample.push_back(static_cast<char>(255));
            std::vector<uint8_t> in(sample.begin(),sample.end());
            auto cpu=cpu_match(in);
            auto ref=compact_tokens(in,cpu);
            auto gotm=gpu_match(in);
            auto got=compact_tokens(in,gotm);
            if (got!=ref || detokenize(got)!=in) throw std::runtime_error("self-test mismatch");
            std::cout<<"SELF_TEST PASS device=\""<<gotm.device_name<<"\" gpu_used="<<(gotm.gpu_used?1:0)
                     <<" match_ms="<<gotm.match_ms<<"\n";
            return 0;
        }
        if (argc!=3) {
            std::cerr<<"usage: khepri_gpu_tokenizer <input> <output> | --self-test\n";
            return 2;
        }
        const auto in=read_file(argv[1]);
        const auto t0=std::chrono::steady_clock::now();
        auto m=gpu_match(in);
        auto out=compact_tokens(in,m);
        const auto t1=std::chrono::steady_clock::now();
        write_file(argv[2],out);
        if (detokenize(out)!=in) throw std::runtime_error("round-trip failed");
        const double total_ms=std::chrono::duration<double,std::milli>(t1-t0).count();
        std::cout<<"GPU_USED "<<(m.gpu_used?1:0)<<"\n"
                 <<"DEVICE "<<m.device_name<<"\n"
                 <<"INPUT_BYTES "<<in.size()<<"\n"
                 <<"OUTPUT_BYTES "<<out.size()<<"\n"
                 <<"MATCH_MS "<<m.match_ms<<"\n"
                 <<"TOTAL_MS "<<total_ms<<"\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr<<"ERROR "<<e.what()<<"\n";
        return 1;
    }
}
