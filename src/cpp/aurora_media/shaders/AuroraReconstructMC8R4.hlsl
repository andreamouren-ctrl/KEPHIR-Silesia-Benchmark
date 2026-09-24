cbuffer Params : register(b0)
{
    uint Width;
    uint Height;
    uint FrameBytes;
    uint BlocksX;
};

Buffer<uint> Previous : register(t0);
Buffer<uint> Residual : register(t1);
Buffer<uint> MotionMap : register(t2);
RWByteAddressBuffer ReconstructedOut : register(u0);

static const int2 MotionCandidates[25] = {
    int2(0,0),
    int2(-2,0), int2(2,0), int2(0,-2), int2(0,2),
    int2(-4,0), int2(4,0),
    int2(-2,-2), int2(2,-2), int2(-2,2), int2(2,2),
    int2(0,-4), int2(0,4),
    int2(-4,-2), int2(4,-2), int2(-4,2), int2(4,2),
    int2(-2,-4), int2(2,-4), int2(-2,4), int2(2,4),
    int2(-4,-4), int2(4,-4), int2(-4,4), int2(4,4)
};

uint reconstruct_at(uint index)
{
    uint yBytes=Width*Height;
    uint chromaWidth=Width/2u;
    uint chromaHeight=Height/2u;
    uint chromaBytes=chromaWidth*chromaHeight;

    uint x;
    uint y;
    uint planeOffset;
    uint stride;
    uint blockX;
    uint blockY;
    int dx;
    int dy;

    if(index<yBytes)
    {
        x=index%Width;
        y=index/Width;
        planeOffset=0u;
        stride=Width;
        blockX=x/8u;
        blockY=y/8u;
        uint motionIndex=MotionMap[blockY*BlocksX+blockX];
        int2 mv=MotionCandidates[motionIndex];
        dx=mv.x;
        dy=mv.y;
    }
    else
    {
        uint local=index-yBytes;
        bool isV=local>=chromaBytes;
        if(isV) local-=chromaBytes;

        x=local%chromaWidth;
        y=local/chromaWidth;
        planeOffset=isV ? (yBytes+chromaBytes) : yBytes;
        stride=chromaWidth;

        blockX=x/4u;
        blockY=y/4u;
        uint motionIndex=MotionMap[blockY*BlocksX+blockX];
        int2 mv=MotionCandidates[motionIndex];
        dx=mv.x/2;
        dy=mv.y/2;
    }

    uint prevIndex=planeOffset+uint(int(y)+dy)*stride+uint(int(x)+dx);
    uint reconstructed=(Previous[prevIndex]+Residual[index])&255u;
    return reconstructed;
}

[numthreads(256,1,1)]
void main(uint3 tid : SV_DispatchThreadID)
{
    uint base=tid.x*4u;
    if(base>=FrameBytes) return;
    uint packed=reconstruct_at(base);
    if(base+1u<FrameBytes) packed|=reconstruct_at(base+1u)<<8u;
    if(base+2u<FrameBytes) packed|=reconstruct_at(base+2u)<<16u;
    if(base+3u<FrameBytes) packed|=reconstruct_at(base+3u)<<24u;
    ReconstructedOut.Store(base,packed);
}
