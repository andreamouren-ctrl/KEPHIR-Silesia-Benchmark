#if defined(_WIN32)

#include "AuroraVideoCompute.h"
#include "AuroraVideoMotion.h"
#include "AuroraMediaError.h"

#include <d3d12.h>
#include <d3dcompiler.h>
#include <dxgi1_6.h>
#include <wrl/client.h>

#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;

#ifndef AURORA_SHADER_DIR
#define AURORA_SHADER_DIR L"src/cpp/aurora_media/shaders"
#endif

namespace aurora::media {
namespace {

void check(HRESULT hr,const char* what) {
    if(FAILED(hr))
        throw AuroraMediaError(ErrorCode::InternalInvariant,
                               std::string("D3D12 failure: ")+what);
}

std::wstring shader_path() {
    std::wstring p=AURORA_SHADER_DIR;
    if(!p.empty() && p.back()!=L'/' && p.back()!=L'\\') p+=L"\\";
    p+=L"AuroraMotionMC8R4.hlsl";
    return p;
}

std::uint64_t align_up(std::uint64_t v,std::uint64_t a) {
    return (v+a-1u)&~(a-1u);
}

ComPtr<ID3D12Resource> make_buffer(ID3D12Device* device,
                                   std::uint64_t bytes,
                                   D3D12_HEAP_TYPE heap,
                                   D3D12_RESOURCE_FLAGS flags,
                                   D3D12_RESOURCE_STATES initial) {
    D3D12_HEAP_PROPERTIES hp{};
    hp.Type=heap;
    hp.CPUPageProperty=D3D12_CPU_PAGE_PROPERTY_UNKNOWN;
    hp.MemoryPoolPreference=D3D12_MEMORY_POOL_UNKNOWN;
    hp.CreationNodeMask=1;
    hp.VisibleNodeMask=1;

    D3D12_RESOURCE_DESC rd{};
    rd.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;
    rd.Alignment=0;
    rd.Width=std::max<std::uint64_t>(bytes,4);
    rd.Height=1;
    rd.DepthOrArraySize=1;
    rd.MipLevels=1;
    rd.Format=DXGI_FORMAT_UNKNOWN;
    rd.SampleDesc.Count=1;
    rd.SampleDesc.Quality=0;
    rd.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    rd.Flags=flags;

    ComPtr<ID3D12Resource> r;
    check(device->CreateCommittedResource(&hp,D3D12_HEAP_FLAG_NONE,&rd,initial,nullptr,
                                          IID_PPV_ARGS(&r)),
          "CreateCommittedResource");
    return r;
}

void upload(ID3D12Resource* r,const void* src,std::size_t n) {
    void* p=nullptr;
    D3D12_RANGE noRead{0,0};
    check(r->Map(0,&noRead,&p),"Map upload");
    std::memcpy(p,src,n);
    r->Unmap(0,nullptr);
}

class D3D12VideoMotionCompute final : public IVideoMotionCompute {
public:
    explicit D3D12VideoMotionCompute(bool forceWarp) {
        UINT flags=0;
        check(CreateDXGIFactory2(flags,IID_PPV_ARGS(&factory_)),"CreateDXGIFactory2");

        if(forceWarp) {
            check(factory_->EnumWarpAdapter(IID_PPV_ARGS(&adapter_)),"EnumWarpAdapter");
            hardware_=false;
        } else {
            for(UINT i=0;;++i) {
                ComPtr<IDXGIAdapter1> a;
                if(factory_->EnumAdapters1(i,&a)==DXGI_ERROR_NOT_FOUND) break;
                DXGI_ADAPTER_DESC1 d{};
                a->GetDesc1(&d);
                if(d.Flags&DXGI_ADAPTER_FLAG_SOFTWARE) continue;
                if(SUCCEEDED(D3D12CreateDevice(a.Get(),D3D_FEATURE_LEVEL_11_0,
                                               __uuidof(ID3D12Device),nullptr))) {
                    check(a.As(&adapter_),"Adapter cast");
                    hardware_=true;
                    break;
                }
            }
            if(!adapter_) {
                check(factory_->EnumWarpAdapter(IID_PPV_ARGS(&adapter_)),"EnumWarpAdapter fallback");
                hardware_=false;
            }
        }

        check(D3D12CreateDevice(adapter_.Get(),D3D_FEATURE_LEVEL_11_0,
                                IID_PPV_ARGS(&device_)),"D3D12CreateDevice");

        DXGI_ADAPTER_DESC desc{};
        adapter_->GetDesc(&desc);
        char name[256]{};
        WideCharToMultiByte(CP_UTF8,0,desc.Description,-1,name,sizeof(name),nullptr,nullptr);
        adapter_name_=name;

        D3D12_COMMAND_QUEUE_DESC qd{};
        qd.Type=D3D12_COMMAND_LIST_TYPE_COMPUTE;
        check(device_->CreateCommandQueue(&qd,IID_PPV_ARGS(&queue_)),"CreateCommandQueue");
        check(device_->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_COMPUTE,
                                               IID_PPV_ARGS(&allocator_)),"CreateCommandAllocator");

        create_pipeline();

        check(device_->CreateFence(0,D3D12_FENCE_FLAG_NONE,IID_PPV_ARGS(&fence_)),"CreateFence");
        event_=CreateEventW(nullptr,FALSE,FALSE,nullptr);
        if(!event_) throw AuroraMediaError(ErrorCode::InternalInvariant,"CreateEvent failed");
    }

    ~D3D12VideoMotionCompute() override {
        if(event_) CloseHandle(event_);
    }

    VideoComputeCapabilities capabilities() const override {
        return VideoComputeCapabilities{
            VideoComputeBackend::D3D12,true,hardware_,adapter_name_
        };
    }

    Bytes motion_map_mc8r4(ByteView cur,ByteView prev,
                           std::uint32_t w,std::uint32_t h) override {
        if(w==0||h==0||(w%8)!=0||(h%8)!=0||(w%2)!=0||(h%2)!=0)
            throw AuroraMediaError(ErrorCode::InvalidArgument,"D3D12 MC8R4 invalid dimensions");
        const std::size_t yBytes=static_cast<std::size_t>(w)*h;
        const std::size_t frameBytes=yBytes+(yBytes/2);
        if(cur.size()!=frameBytes||prev.size()!=frameBytes)
            throw AuroraMediaError(ErrorCode::InvalidArgument,"D3D12 MC8R4 frame size mismatch");

        const std::uint32_t blocksX=w/8;
        const std::uint32_t blocksY=h/8;
        const std::size_t blockCount=static_cast<std::size_t>(blocksX)*blocksY;
        const std::size_t outBytes=blockCount*sizeof(std::uint32_t);

        auto curUpload=make_buffer(device_.Get(),yBytes,D3D12_HEAP_TYPE_UPLOAD,
                                   D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_GENERIC_READ);
        auto prevUpload=make_buffer(device_.Get(),yBytes,D3D12_HEAP_TYPE_UPLOAD,
                                    D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_GENERIC_READ);
        auto curBuf=make_buffer(device_.Get(),yBytes,D3D12_HEAP_TYPE_DEFAULT,
                                D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_COPY_DEST);
        auto prevBuf=make_buffer(device_.Get(),yBytes,D3D12_HEAP_TYPE_DEFAULT,
                                 D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_COPY_DEST);
        auto outBuf=make_buffer(device_.Get(),outBytes,D3D12_HEAP_TYPE_DEFAULT,
                                D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS,
                                D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
        auto readback=make_buffer(device_.Get(),outBytes,D3D12_HEAP_TYPE_READBACK,
                                  D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_COPY_DEST);

        D3D12_DESCRIPTOR_HEAP_DESC hd{};
        hd.Type=D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
        hd.NumDescriptors=2;
        hd.Flags=D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
        ComPtr<ID3D12DescriptorHeap> srvHeap;
        check(device_->CreateDescriptorHeap(&hd,IID_PPV_ARGS(&srvHeap)),"CreateDescriptorHeap");

        const auto inc=device_->GetDescriptorHandleIncrementSize(
            D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
        auto cpu0=srvHeap->GetCPUDescriptorHandleForHeapStart();

        D3D12_SHADER_RESOURCE_VIEW_DESC sd{};
        sd.Format=DXGI_FORMAT_R32_TYPELESS;
        sd.ViewDimension=D3D12_SRV_DIMENSION_BUFFER;
        sd.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
        sd.Buffer.FirstElement=0;
        sd.Buffer.NumElements=static_cast<UINT>(yBytes/4);
        sd.Buffer.StructureByteStride=0;
        sd.Buffer.Flags=D3D12_BUFFER_SRV_FLAG_RAW;

        device_->CreateShaderResourceView(curBuf.Get(),&sd,cpu0);
        auto cpu1=cpu0;
        cpu1.ptr+=inc;
        device_->CreateShaderResourceView(prevBuf.Get(),&sd,cpu1);

        upload(curUpload.Get(),cur.data(),yBytes);
        upload(prevUpload.Get(),prev.data(),yBytes);

        check(allocator_->Reset(),"Allocator Reset");
        check(command_list_->Reset(allocator_.Get(),pso_.Get()),"CommandList Reset");

        command_list_->CopyBufferRegion(curBuf.Get(),0,curUpload.Get(),0,yBytes);
        command_list_->CopyBufferRegion(prevBuf.Get(),0,prevUpload.Get(),0,yBytes);

        D3D12_RESOURCE_BARRIER inputBarriers[2]{};
        inputBarriers[0].Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        inputBarriers[0].Transition.pResource=curBuf.Get();
        inputBarriers[0].Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_DEST;
        inputBarriers[0].Transition.StateAfter=D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
        inputBarriers[0].Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        inputBarriers[1]=inputBarriers[0];
        inputBarriers[1].Transition.pResource=prevBuf.Get();
        command_list_->ResourceBarrier(2,inputBarriers);

        ID3D12DescriptorHeap* heaps[]{srvHeap.Get()};
        command_list_->SetDescriptorHeaps(1,heaps);
        command_list_->SetComputeRootSignature(root_.Get());

        const std::array<std::uint32_t,4> constants{w,h,blocksX,blocksY};
        command_list_->SetComputeRoot32BitConstants(0,4,constants.data(),0);
        auto gpu0=srvHeap->GetGPUDescriptorHandleForHeapStart();
        auto gpu1=gpu0;
        gpu1.ptr+=inc;
        command_list_->SetComputeRootDescriptorTable(1,gpu0);
        command_list_->SetComputeRootDescriptorTable(2,gpu1);
        command_list_->SetComputeRootUnorderedAccessView(3,outBuf->GetGPUVirtualAddress());

        command_list_->Dispatch(blocksX,blocksY,1);

        D3D12_RESOURCE_BARRIER barrier{};
        barrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        barrier.Transition.pResource=outBuf.Get();
        barrier.Transition.StateBefore=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
        barrier.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;
        barrier.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        command_list_->ResourceBarrier(1,&barrier);
        command_list_->CopyBufferRegion(readback.Get(),0,outBuf.Get(),0,outBytes);
        check(command_list_->Close(),"CommandList Close");

        ID3D12CommandList* lists[]{command_list_.Get()};
        queue_->ExecuteCommandLists(1,lists);

        const auto fv=++fence_value_;
        check(queue_->Signal(fence_.Get(),fv),"Queue Signal");
        if(fence_->GetCompletedValue()<fv) {
            check(fence_->SetEventOnCompletion(fv,event_),"SetEventOnCompletion");
            WaitForSingleObject(event_,INFINITE);
        }

        void* mapped=nullptr;
        D3D12_RANGE readRange{0,outBytes};
        check(readback->Map(0,&readRange,&mapped),"Map readback");
        const auto* p=static_cast<const std::uint32_t*>(mapped);
        Bytes result(blockCount);
        for(std::size_t i=0;i<blockCount;++i) {
            result[i]=static_cast<Byte>(p[i] & 0xffu);
            if(i==18 || i==33) {
                if(i==18) {
                    std::cerr<<"GPUDBG block="<<i
                             <<" idx="<<(p[i]&0xffu)
                             <<" prev_byte="<<((p[i]>>8u)&0xffu)
                             <<" cur_byte="<<((p[i]>>16u)&0xffu)<<"\\n";
                } else {
                    std::cerr<<"GPUDBG block="<<i
                             <<" idx="<<(p[i]&0xffu)
                             <<" sad="<<(p[i]>>8u)<<"\\n";
                }
            }
        }
        D3D12_RANGE noWrite{0,0};
        readback->Unmap(0,&noWrite);
        return result;
    }

private:
    void create_pipeline() {
        D3D12_ROOT_PARAMETER rp[4]{};
        rp[0].ParameterType=D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
        rp[0].Constants.ShaderRegister=0;
        rp[0].Constants.RegisterSpace=0;
        rp[0].Constants.Num32BitValues=4;
        rp[0].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;

        D3D12_DESCRIPTOR_RANGE ranges[2]{};
        for(int i=0;i<2;++i) {
            ranges[i].RangeType=D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
            ranges[i].NumDescriptors=1;
            ranges[i].BaseShaderRegister=static_cast<UINT>(i);
            ranges[i].RegisterSpace=0;
            ranges[i].OffsetInDescriptorsFromTableStart=0;

            rp[i+1].ParameterType=D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
            rp[i+1].DescriptorTable.NumDescriptorRanges=1;
            rp[i+1].DescriptorTable.pDescriptorRanges=&ranges[i];
            rp[i+1].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;
        }
        rp[3].ParameterType=D3D12_ROOT_PARAMETER_TYPE_UAV;
        rp[3].Descriptor.ShaderRegister=0;
        rp[3].Descriptor.RegisterSpace=0;
        rp[3].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;

        D3D12_ROOT_SIGNATURE_DESC rsd{};
        rsd.NumParameters=4;
        rsd.pParameters=rp;
        rsd.Flags=D3D12_ROOT_SIGNATURE_FLAG_NONE;

        ComPtr<ID3DBlob> rsBlob,error;
        check(D3D12SerializeRootSignature(&rsd,D3D_ROOT_SIGNATURE_VERSION_1,
                                          &rsBlob,&error),"SerializeRootSignature");
        check(device_->CreateRootSignature(0,rsBlob->GetBufferPointer(),rsBlob->GetBufferSize(),
                                           IID_PPV_ARGS(&root_)),"CreateRootSignature");

        UINT compileFlags=D3DCOMPILE_OPTIMIZATION_LEVEL3;
        ComPtr<ID3DBlob> shader,errors;
        const auto path=shader_path();
        const auto hr=D3DCompileFromFile(path.c_str(),nullptr,D3D_COMPILE_STANDARD_FILE_INCLUDE,
                                         "main","cs_5_1",compileFlags,0,&shader,&errors);
        if(FAILED(hr)) {
            std::string msg="D3DCompileFromFile";
            if(errors) msg+=": "+std::string(static_cast<const char*>(errors->GetBufferPointer()),
                                             errors->GetBufferSize());
            throw AuroraMediaError(ErrorCode::InternalInvariant,msg);
        }

        D3D12_COMPUTE_PIPELINE_STATE_DESC pd{};
        pd.pRootSignature=root_.Get();
        pd.CS={shader->GetBufferPointer(),shader->GetBufferSize()};
        check(device_->CreateComputePipelineState(&pd,IID_PPV_ARGS(&pso_)),
              "CreateComputePipelineState");

        check(device_->CreateCommandList(0,D3D12_COMMAND_LIST_TYPE_COMPUTE,
                                         allocator_.Get(),pso_.Get(),
                                         IID_PPV_ARGS(&command_list_)),"CreateCommandList");
        check(command_list_->Close(),"Initial CommandList Close");
    }

    ComPtr<IDXGIFactory6> factory_;
    ComPtr<IDXGIAdapter4> adapter_;
    ComPtr<ID3D12Device> device_;
    ComPtr<ID3D12CommandQueue> queue_;
    ComPtr<ID3D12CommandAllocator> allocator_;
    ComPtr<ID3D12GraphicsCommandList> command_list_;
    ComPtr<ID3D12RootSignature> root_;
    ComPtr<ID3D12PipelineState> pso_;
    ComPtr<ID3D12Fence> fence_;
    HANDLE event_{};
    std::uint64_t fence_value_{};
    bool hardware_{};
    std::string adapter_name_;
};

} // namespace

std::unique_ptr<IVideoMotionCompute> make_d3d12_video_motion_compute(bool force_warp) {
    return std::make_unique<D3D12VideoMotionCompute>(force_warp);
}

} // namespace aurora::media

#endif
