cbuffer Params : register(b0)
{
    uint Width;
    uint Height;
    uint BlocksX;
    uint BlocksY;
};

ByteAddressBuffer CurrentY : register(t0);
ByteAddressBuffer PreviousY : register(t1);
StructuredBuffer<int2> Candidates : register(t2);
RWStructuredBuffer<uint> MotionOut : register(u0);

uint LoadByte(ByteAddressBuffer b, uint index)
{
    uint word = b.Load(index & ~3u);
    uint shift = (index & 3u) * 8u;
    return (word >> shift) & 0xffu;
}

[numthreads(8, 8, 1)]
void main(uint3 tid : SV_DispatchThreadID)
{
    uint bxBlock = tid.x;
    uint byBlock = tid.y;
    if (bxBlock >= BlocksX || byBlock >= BlocksY)
        return;

    uint bx = bxBlock * 8u;
    uint by = byBlock * 8u;

    uint bestIndex = 0u;
    uint bestCost = 0xffffffffu;
    bool found = false;

    [unroll]
    for (uint ci = 0u; ci < 25u; ++ci)
    {
        int2 mv = Candidates[ci];
        int sx = int(bx) + mv.x;
        int sy = int(by) + mv.y;

        if (sx < 0 || sy < 0 ||
            sx + 8 > int(Width) || sy + 8 > int(Height))
            continue;

        uint cost = 0u;
        [unroll]
        for (uint yy = 0u; yy < 8u; ++yy)
        {
            [unroll]
            for (uint xx = 0u; xx < 8u; ++xx)
            {
                uint a = LoadByte(CurrentY, (by + yy) * Width + (bx + xx));
                uint b = LoadByte(PreviousY, uint(sy + int(yy)) * Width + uint(sx + int(xx)));
                cost += (a > b) ? (a - b) : (b - a);
            }
        }

        if (!found || cost < bestCost)
        {
            found = true;
            bestCost = cost;
            bestIndex = ci;
        }
    }

    MotionOut[byBlock * BlocksX + bxBlock] = bestIndex;
}
