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
    struct ThreeInputCache {
        std::size_t frame_bytes{};
        std::size_t block_count{};
        std::array<ComPtr<ID3D12Resource>,3> upload;
        std::array<ComPtr<ID3D12Resource>,3> input;
        ComPtr<ID3D12Resource> output;
        ComPtr<ID3D12Resource> readback;
        ComPtr<ID3D12DescriptorHeap> heap;
        bool has_completed_work{};
    };

    struct MotionCache {
        std::size_t y_bytes{};
        std::size_t out_bytes{};
        std::array<ComPtr<ID3D12Resource>,2> upload;
        std::array<ComPtr<ID3D12Resource>,2> input;
        ComPtr<ID3D12Resource> output;
        ComPtr<ID3D12Resource> readback;
        ComPtr<ID3D12DescriptorHeap> heap;
        bool has_completed_work{};
    };

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
        create_three_input_pipeline(L"AuroraResidualMC8R4.hlsl",
                                    residual_root_,residual_pso_,
                                    residual_allocator_,residual_command_list_);
        create_three_input_pipeline(L"AuroraReconstructMC8R4.hlsl",
                                    reconstruct_root_,reconstruct_pso_,
                                    reconstruct_allocator_,reconstruct_command_list_);

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

        ensure_motion_cache(yBytes,outBytes);
        auto& cache=motion_cache_;
        const auto inc=device_->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
        upload(cache.upload[0].Get(),cur.data(),yBytes);
        upload(cache.upload[1].Get(),prev.data(),yBytes);

        check(allocator_->Reset(),"Allocator Reset");
        check(command_list_->Reset(allocator_.Get(),pso_.Get()),"CommandList Reset");

        D3D12_RESOURCE_BARRIER inputBarriers[2]{};
        for(int i=0;i<2;++i) {
            inputBarriers[i].Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
            inputBarriers[i].Transition.pResource=cache.input[i].Get();
            inputBarriers[i].Transition.StateBefore=cache.has_completed_work
                ? D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE
                : D3D12_RESOURCE_STATE_COPY_DEST;
            inputBarriers[i].Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_DEST;
            inputBarriers[i].Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        }
        if(cache.has_completed_work)
            command_list_->ResourceBarrier(2,inputBarriers);
        command_list_->CopyBufferRegion(cache.input[0].Get(),0,cache.upload[0].Get(),0,yBytes);
        command_list_->CopyBufferRegion(cache.input[1].Get(),0,cache.upload[1].Get(),0,yBytes);
        for(int i=0;i<2;++i) {
            inputBarriers[i].Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_DEST;
            inputBarriers[i].Transition.StateAfter=D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
        }
        command_list_->ResourceBarrier(2,inputBarriers);

        if(cache.has_completed_work) {
            D3D12_RESOURCE_BARRIER outputReset{};
            outputReset.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
            outputReset.Transition.pResource=cache.output.Get();
            outputReset.Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_SOURCE;
            outputReset.Transition.StateAfter=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
            outputReset.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
            command_list_->ResourceBarrier(1,&outputReset);
        }

        ID3D12DescriptorHeap* heaps[]{cache.heap.Get()};
        command_list_->SetDescriptorHeaps(1,heaps);
        command_list_->SetComputeRootSignature(root_.Get());

        const std::array<std::uint32_t,4> constants{w,h,blocksX,blocksY};
        command_list_->SetComputeRoot32BitConstants(0,4,constants.data(),0);
        auto gpu0=cache.heap->GetGPUDescriptorHandleForHeapStart();
        auto gpu1=gpu0;
        gpu1.ptr+=inc;
        command_list_->SetComputeRootDescriptorTable(1,gpu0);
        command_list_->SetComputeRootDescriptorTable(2,gpu1);
        command_list_->SetComputeRootUnorderedAccessView(3,cache.output->GetGPUVirtualAddress());

        command_list_->Dispatch(blocksX,blocksY,1);

        D3D12_RESOURCE_BARRIER barrier{};
        barrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        barrier.Transition.pResource=cache.output.Get();
        barrier.Transition.StateBefore=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
        barrier.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;
        barrier.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        command_list_->ResourceBarrier(1,&barrier);
        command_list_->CopyBufferRegion(cache.readback.Get(),0,cache.output.Get(),0,outBytes);
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
        check(cache.readback->Map(0,&readRange,&mapped),"Map readback");
        const auto* p=static_cast<const std::uint32_t*>(mapped);
        Bytes result(blockCount);
        for(std::size_t i=0;i<blockCount;++i) {
            result[i]=static_cast<Byte>(p[i] & 0xffu);
        }
        D3D12_RANGE noWrite{0,0};
        cache.readback->Unmap(0,&noWrite);
        cache.has_completed_work=true;
        return result;
    }


    Bytes residual_yuv420_mc8r4(ByteView cur,ByteView prev,
                                ByteView motion,
                                std::uint32_t w,std::uint32_t h) override {
        if(w==0||h==0||(w%8)!=0||(h%8)!=0||(w%2)!=0||(h%2)!=0)
            throw AuroraMediaError(ErrorCode::InvalidArgument,"D3D12 residual invalid dimensions");

        const std::size_t yBytes=static_cast<std::size_t>(w)*h;
        const std::size_t frameBytes=yBytes+(yBytes/2);
        const std::size_t blockCount=static_cast<std::size_t>(w/8)*(h/8);
        if(cur.size()!=frameBytes||prev.size()!=frameBytes||motion.size()!=blockCount)
            throw AuroraMediaError(ErrorCode::InvalidArgument,"D3D12 residual input size mismatch");

        ensure_three_input_cache(residual_cache_,frameBytes,blockCount);
        auto& cache=residual_cache_;
        const std::size_t outBytes=frameBytes;
        upload(cache.upload[0].Get(),cur.data(),frameBytes);
        upload(cache.upload[1].Get(),prev.data(),frameBytes);
        upload(cache.upload[2].Get(),motion.data(),blockCount);
        const auto inc=device_->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);

        check(residual_allocator_->Reset(),"Residual Allocator Reset");
        check(residual_command_list_->Reset(residual_allocator_.Get(),residual_pso_.Get()),
              "Residual CommandList Reset");
        auto* list=residual_command_list_.Get();

        D3D12_RESOURCE_BARRIER barriers[3]{};
        ID3D12Resource* inputs[3]{cache.input[0].Get(),cache.input[1].Get(),cache.input[2].Get()};
        for(int i=0;i<3;++i) {
            barriers[i].Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
            barriers[i].Transition.pResource=inputs[i];
            barriers[i].Transition.StateBefore=cache.has_completed_work
                ? D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE
                : D3D12_RESOURCE_STATE_COPY_DEST;
            barriers[i].Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_DEST;
            barriers[i].Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        }
        if(cache.has_completed_work)
            list->ResourceBarrier(3,barriers);
        list->CopyBufferRegion(cache.input[0].Get(),0,cache.upload[0].Get(),0,frameBytes);
        list->CopyBufferRegion(cache.input[1].Get(),0,cache.upload[1].Get(),0,frameBytes);
        list->CopyBufferRegion(cache.input[2].Get(),0,cache.upload[2].Get(),0,blockCount);
        for(int i=0;i<3;++i) {
            barriers[i].Transition.StateAfter=D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
            barriers[i].Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_DEST;
        }
        list->ResourceBarrier(3,barriers);

        if(cache.has_completed_work) {
            D3D12_RESOURCE_BARRIER outputReset{};
            outputReset.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
            outputReset.Transition.pResource=cache.output.Get();
            outputReset.Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_SOURCE;
            outputReset.Transition.StateAfter=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
            outputReset.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
            list->ResourceBarrier(1,&outputReset);
        }

        ID3D12DescriptorHeap* heaps[]{cache.heap.Get()};
        list->SetDescriptorHeaps(1,heaps);
        list->SetComputeRootSignature(residual_root_.Get());
        const std::array<std::uint32_t,4> constants{
            w,h,static_cast<std::uint32_t>(frameBytes),w/8
        };
        list->SetComputeRoot32BitConstants(0,4,constants.data(),0);
        auto gpu=cache.heap->GetGPUDescriptorHandleForHeapStart();
        for(int i=0;i<3;++i) {
            list->SetComputeRootDescriptorTable(i+1,gpu);
            gpu.ptr+=inc;
        }
        list->SetComputeRootUnorderedAccessView(4,cache.output->GetGPUVirtualAddress());
        list->Dispatch(static_cast<UINT>((((frameBytes+3)/4)+255)/256),1,1);

        D3D12_RESOURCE_BARRIER outBarrier{};
        outBarrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        outBarrier.Transition.pResource=cache.output.Get();
        outBarrier.Transition.StateBefore=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
        outBarrier.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;
        outBarrier.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        list->ResourceBarrier(1,&outBarrier);
        list->CopyBufferRegion(cache.readback.Get(),0,cache.output.Get(),0,outBytes);
        check(list->Close(),"Residual CommandList Close");

        ID3D12CommandList* lists[]{list};
        queue_->ExecuteCommandLists(1,lists);
        const auto fv=++fence_value_;
        check(queue_->Signal(fence_.Get(),fv),"Residual Queue Signal");
        if(fence_->GetCompletedValue()<fv) {
            check(fence_->SetEventOnCompletion(fv,event_),"Residual SetEventOnCompletion");
            WaitForSingleObject(event_,INFINITE);
        }

        void* mapped=nullptr;
        D3D12_RANGE rr{0,outBytes};
        check(cache.readback->Map(0,&rr,&mapped),"Residual Map readback");
        const auto* u=static_cast<const Byte*>(mapped);
        Bytes result(u,u+frameBytes);
        D3D12_RANGE nw{0,0};
        cache.readback->Unmap(0,&nw);
        cache.has_completed_work=true;
        return result;
    }


    Bytes reconstruct_yuv420_mc8r4(ByteView prev,
                                   ByteView residual,
                                   ByteView motion,
                                   std::uint32_t w,std::uint32_t h) override {
        if(w==0||h==0||(w%8)!=0||(h%8)!=0||(w%2)!=0||(h%2)!=0)
            throw AuroraMediaError(ErrorCode::InvalidArgument,"D3D12 reconstruct invalid dimensions");

        const std::size_t yBytes=static_cast<std::size_t>(w)*h;
        const std::size_t frameBytes=yBytes+(yBytes/2);
        const std::size_t blockCount=static_cast<std::size_t>(w/8)*(h/8);
        if(prev.size()!=frameBytes||residual.size()!=frameBytes||motion.size()!=blockCount)
            throw AuroraMediaError(ErrorCode::InvalidArgument,"D3D12 reconstruct input size mismatch");

        ensure_three_input_cache(reconstruct_cache_,frameBytes,blockCount);
        auto& cache=reconstruct_cache_;
        const std::size_t outBytes=frameBytes;
        upload(cache.upload[0].Get(),prev.data(),frameBytes);
        upload(cache.upload[1].Get(),residual.data(),frameBytes);
        upload(cache.upload[2].Get(),motion.data(),blockCount);
        const auto inc=device_->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);

        check(reconstruct_allocator_->Reset(),"Reconstruct Allocator Reset");
        check(reconstruct_command_list_->Reset(reconstruct_allocator_.Get(),reconstruct_pso_.Get()),
              "Reconstruct CommandList Reset");
        auto* list=reconstruct_command_list_.Get();

        D3D12_RESOURCE_BARRIER barriers[3]{};
        ID3D12Resource* inputs[3]{cache.input[0].Get(),cache.input[1].Get(),cache.input[2].Get()};
        for(int i=0;i<3;++i) {
            barriers[i].Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
            barriers[i].Transition.pResource=inputs[i];
            barriers[i].Transition.StateBefore=cache.has_completed_work
                ? D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE
                : D3D12_RESOURCE_STATE_COPY_DEST;
            barriers[i].Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_DEST;
            barriers[i].Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        }
        if(cache.has_completed_work)
            list->ResourceBarrier(3,barriers);
        list->CopyBufferRegion(cache.input[0].Get(),0,cache.upload[0].Get(),0,frameBytes);
        list->CopyBufferRegion(cache.input[1].Get(),0,cache.upload[1].Get(),0,frameBytes);
        list->CopyBufferRegion(cache.input[2].Get(),0,cache.upload[2].Get(),0,blockCount);
        for(int i=0;i<3;++i) {
            barriers[i].Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_DEST;
            barriers[i].Transition.StateAfter=D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
        }
        list->ResourceBarrier(3,barriers);

        if(cache.has_completed_work) {
            D3D12_RESOURCE_BARRIER outputReset{};
            outputReset.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
            outputReset.Transition.pResource=cache.output.Get();
            outputReset.Transition.StateBefore=D3D12_RESOURCE_STATE_COPY_SOURCE;
            outputReset.Transition.StateAfter=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
            outputReset.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
            list->ResourceBarrier(1,&outputReset);
        }

        ID3D12DescriptorHeap* heaps[]{cache.heap.Get()};
        list->SetDescriptorHeaps(1,heaps);
        list->SetComputeRootSignature(reconstruct_root_.Get());
        const std::array<std::uint32_t,4> constants{
            w,h,static_cast<std::uint32_t>(frameBytes),w/8
        };
        list->SetComputeRoot32BitConstants(0,4,constants.data(),0);
        auto gpu=cache.heap->GetGPUDescriptorHandleForHeapStart();
        for(int i=0;i<3;++i) {
            list->SetComputeRootDescriptorTable(i+1,gpu);
            gpu.ptr+=inc;
        }
        list->SetComputeRootUnorderedAccessView(4,cache.output->GetGPUVirtualAddress());
        list->Dispatch(static_cast<UINT>((((frameBytes+3)/4)+255)/256),1,1);

        D3D12_RESOURCE_BARRIER outBarrier{};
        outBarrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        outBarrier.Transition.pResource=cache.output.Get();
        outBarrier.Transition.StateBefore=D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
        outBarrier.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;
        outBarrier.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        list->ResourceBarrier(1,&outBarrier);
        list->CopyBufferRegion(cache.readback.Get(),0,cache.output.Get(),0,outBytes);
        check(list->Close(),"Reconstruct CommandList Close");

        ID3D12CommandList* lists[]{list};
        queue_->ExecuteCommandLists(1,lists);
        const auto fv=++fence_value_;
        check(queue_->Signal(fence_.Get(),fv),"Reconstruct Queue Signal");
        if(fence_->GetCompletedValue()<fv) {
            check(fence_->SetEventOnCompletion(fv,event_),"Reconstruct SetEventOnCompletion");
            WaitForSingleObject(event_,INFINITE);
        }

        void* mapped=nullptr;
        D3D12_RANGE rr{0,outBytes};
        check(cache.readback->Map(0,&rr,&mapped),"Reconstruct Map readback");
        const auto* u=static_cast<const Byte*>(mapped);
        Bytes result(u,u+frameBytes);
        D3D12_RANGE nw{0,0};
        cache.readback->Unmap(0,&nw);
        cache.has_completed_work=true;
        return result;
    }

private:
    void ensure_motion_cache(std::size_t y_bytes,std::size_t out_bytes) {
        if(motion_cache_.y_bytes==y_bytes && motion_cache_.out_bytes==out_bytes && motion_cache_.heap)
            return;
        motion_cache_={};
        motion_cache_.y_bytes=y_bytes;
        motion_cache_.out_bytes=out_bytes;
        for(std::size_t i=0;i<2;++i) {
            motion_cache_.upload[i]=make_buffer(device_.Get(),y_bytes,D3D12_HEAP_TYPE_UPLOAD,
                                                 D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_GENERIC_READ);
            motion_cache_.input[i]=make_buffer(device_.Get(),y_bytes,D3D12_HEAP_TYPE_DEFAULT,
                                                D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_COPY_DEST);
        }
        motion_cache_.output=make_buffer(device_.Get(),out_bytes,D3D12_HEAP_TYPE_DEFAULT,
                                         D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS,
                                         D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
        motion_cache_.readback=make_buffer(device_.Get(),out_bytes,D3D12_HEAP_TYPE_READBACK,
                                           D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_COPY_DEST);
        D3D12_DESCRIPTOR_HEAP_DESC hd{};
        hd.Type=D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
        hd.NumDescriptors=2;
        hd.Flags=D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
        check(device_->CreateDescriptorHeap(&hd,IID_PPV_ARGS(&motion_cache_.heap)),"Motion cached descriptor heap");
        const auto inc=device_->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
        auto handle=motion_cache_.heap->GetCPUDescriptorHandleForHeapStart();
        for(std::size_t i=0;i<2;++i) {
            D3D12_SHADER_RESOURCE_VIEW_DESC sd{};
            sd.Format=DXGI_FORMAT_R8_UINT;
            sd.ViewDimension=D3D12_SRV_DIMENSION_BUFFER;
            sd.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
            sd.Buffer.NumElements=static_cast<UINT>(y_bytes);
            device_->CreateShaderResourceView(motion_cache_.input[i].Get(),&sd,handle);
            handle.ptr+=inc;
        }
    }

    void ensure_three_input_cache(ThreeInputCache& cache,
                                  std::size_t frame_bytes,
                                  std::size_t block_count) {
        if(cache.frame_bytes==frame_bytes && cache.block_count==block_count && cache.heap)
            return;

        cache={};
        cache.frame_bytes=frame_bytes;
        cache.block_count=block_count;
        const std::array<std::size_t,3> sizes{frame_bytes,frame_bytes,block_count};
        for(std::size_t i=0;i<sizes.size();++i) {
            cache.upload[i]=make_buffer(device_.Get(),sizes[i],D3D12_HEAP_TYPE_UPLOAD,
                                        D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_GENERIC_READ);
            cache.input[i]=make_buffer(device_.Get(),sizes[i],D3D12_HEAP_TYPE_DEFAULT,
                                       D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_COPY_DEST);
        }
        cache.output=make_buffer(device_.Get(),frame_bytes,D3D12_HEAP_TYPE_DEFAULT,
                                 D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS,
                                 D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
        cache.readback=make_buffer(device_.Get(),frame_bytes,D3D12_HEAP_TYPE_READBACK,
                                   D3D12_RESOURCE_FLAG_NONE,D3D12_RESOURCE_STATE_COPY_DEST);

        D3D12_DESCRIPTOR_HEAP_DESC hd{};
        hd.Type=D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
        hd.NumDescriptors=3;
        hd.Flags=D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
        check(device_->CreateDescriptorHeap(&hd,IID_PPV_ARGS(&cache.heap)),"Cached CreateDescriptorHeap");
        const auto inc=device_->GetDescriptorHandleIncrementSize(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
        auto handle=cache.heap->GetCPUDescriptorHandleForHeapStart();
        for(std::size_t i=0;i<sizes.size();++i) {
            D3D12_SHADER_RESOURCE_VIEW_DESC sd{};
            sd.Format=DXGI_FORMAT_R8_UINT;
            sd.ViewDimension=D3D12_SRV_DIMENSION_BUFFER;
            sd.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
            sd.Buffer.FirstElement=0;
            sd.Buffer.NumElements=static_cast<UINT>(sizes[i]);
            device_->CreateShaderResourceView(cache.input[i].Get(),&sd,handle);
            handle.ptr+=inc;
        }
    }

    void create_three_input_pipeline(
        const wchar_t* shader_name,
        ComPtr<ID3D12RootSignature>& root,
        ComPtr<ID3D12PipelineState>& pso,
        ComPtr<ID3D12CommandAllocator>& allocator,
        ComPtr<ID3D12GraphicsCommandList>& command_list) {
        D3D12_ROOT_PARAMETER rp[5]{};
        rp[0].ParameterType=D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
        rp[0].Constants.ShaderRegister=0;
        rp[0].Constants.Num32BitValues=4;
        rp[0].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;

        D3D12_DESCRIPTOR_RANGE ranges[3]{};
        for(int i=0;i<3;++i) {
            ranges[i].RangeType=D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
            ranges[i].NumDescriptors=1;
            ranges[i].BaseShaderRegister=static_cast<UINT>(i);
            ranges[i].OffsetInDescriptorsFromTableStart=0;
            rp[i+1].ParameterType=D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
            rp[i+1].DescriptorTable.NumDescriptorRanges=1;
            rp[i+1].DescriptorTable.pDescriptorRanges=&ranges[i];
            rp[i+1].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;
        }
        rp[4].ParameterType=D3D12_ROOT_PARAMETER_TYPE_UAV;
        rp[4].Descriptor.ShaderRegister=0;
        rp[4].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;

        D3D12_ROOT_SIGNATURE_DESC rsd{};
        rsd.NumParameters=5;
        rsd.pParameters=rp;

        ComPtr<ID3DBlob> rsBlob,rsErr;
        check(D3D12SerializeRootSignature(&rsd,D3D_ROOT_SIGNATURE_VERSION_1,
                                          &rsBlob,&rsErr),
              "Aux SerializeRootSignature");
        check(device_->CreateRootSignature(0,rsBlob->GetBufferPointer(),rsBlob->GetBufferSize(),
                                           IID_PPV_ARGS(&root)),
              "Aux CreateRootSignature");

        std::wstring shaderPath=AURORA_SHADER_DIR;
        if(!shaderPath.empty()&&shaderPath.back()!=L'/'&&shaderPath.back()!=L'\\')
            shaderPath+=L"\\";
        shaderPath+=shader_name;

        ComPtr<ID3DBlob> shader,errors;
        const auto hr=D3DCompileFromFile(shaderPath.c_str(),nullptr,
                                         D3D_COMPILE_STANDARD_FILE_INCLUDE,
                                         "main","cs_5_1",
                                         D3DCOMPILE_OPTIMIZATION_LEVEL3,0,
                                         &shader,&errors);
        if(FAILED(hr)) {
            std::string msg="Aux D3DCompileFromFile";
            if(errors) msg+=": "+std::string(
                static_cast<const char*>(errors->GetBufferPointer()),
                errors->GetBufferSize());
            throw AuroraMediaError(ErrorCode::InternalInvariant,msg);
        }

        D3D12_COMPUTE_PIPELINE_STATE_DESC pd{};
        pd.pRootSignature=root.Get();
        pd.CS={shader->GetBufferPointer(),shader->GetBufferSize()};
        check(device_->CreateComputePipelineState(&pd,IID_PPV_ARGS(&pso)),
              "Aux CreateComputePipelineState");

        check(device_->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_COMPUTE,
                                               IID_PPV_ARGS(&allocator)),
              "Aux CreateCommandAllocator");
        check(device_->CreateCommandList(0,D3D12_COMMAND_LIST_TYPE_COMPUTE,
                                         allocator.Get(),pso.Get(),
                                         IID_PPV_ARGS(&command_list)),
              "Aux CreateCommandList");
        check(command_list->Close(),"Aux Initial CommandList Close");
    }

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

    ComPtr<ID3D12RootSignature> residual_root_;
    ComPtr<ID3D12PipelineState> residual_pso_;
    ComPtr<ID3D12CommandAllocator> residual_allocator_;
    ComPtr<ID3D12GraphicsCommandList> residual_command_list_;

    ComPtr<ID3D12RootSignature> reconstruct_root_;
    ComPtr<ID3D12PipelineState> reconstruct_pso_;
    ComPtr<ID3D12CommandAllocator> reconstruct_allocator_;
    ComPtr<ID3D12GraphicsCommandList> reconstruct_command_list_;

    MotionCache motion_cache_;
    ThreeInputCache residual_cache_;
    ThreeInputCache reconstruct_cache_;

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
