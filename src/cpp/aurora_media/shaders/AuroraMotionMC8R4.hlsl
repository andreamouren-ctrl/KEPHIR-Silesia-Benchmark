cbuffer Params : register(b0)
{
    uint Width;
    uint Height;
    uint BlocksX;
    uint BlocksY;
};

ByteAddressBuffer CurrentY : register(t0);
ByteAddressBuffer PreviousY : register(t1);
RWByteAddressBuffer MotionOut : register(u0);

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

groupshared uint CandidateCost[32];

uint LoadByte(ByteAddressBuffer b, uint index)
{
    uint word = b.Load(index & ~3u);
    uint shift = (index & 3u) * 8u;
    return (word >> shift) & 0xffu;
}

[numthreads(32, 1, 1)]
void main(uint3 gid : SV_GroupID, uint3 gtid : SV_GroupThreadID)
{
    uint bxBlock = gid.x;
    uint byBlock = gid.y;
    uint ci = gtid.x;

    if (bxBlock >= BlocksX || byBlock >= BlocksY)
        return;

    uint cost = 0xffffffffu;

    if (ci < 25u)
    {
        uint bx = bxBlock * 8u;
        uint by = byBlock * 8u;
        int2 mv = MotionCandidates[ci];
        int sx = int(bx) + mv.x;
        int sy = int(by) + mv.y;

        if (sx >= 0 && sy >= 0 &&
            sx + 8 <= int(Width) && sy + 8 <= int(Height))
        {
            cost = 0u;
            [unroll]
            for (uint yy = 0u; yy < 8u; ++yy)
            {
                [unroll]
                for (uint xx = 0u; xx < 8u; ++xx)
                {
                    uint a = LoadByte(CurrentY, (by + yy) * Width + (bx + xx));
                    uint b = LoadByte(PreviousY,
                        uint(sy + int(yy)) * Width + uint(sx + int(xx)));
                    cost += (a > b) ? (a - b) : (b - a);
                }
            }
        }
    }

    CandidateCost[ci] = cost;
    GroupMemoryBarrierWithGroupSync();

    if (ci == 0u)
    {
        uint bestIndex = 0u;
        uint bestCost = 0xffffffffu;

        [unroll]
        for (uint i = 0u; i < 25u; ++i)
        {
            uint c = CandidateCost[i];
            if (c < bestCost)
            {
                bestCost = c;
                bestIndex = i;
            }
        }

        MotionOut.Store((byBlock * BlocksX + bxBlock) * 4u, bestIndex);
        if (bxBlock == 18u && byBlock == 0u)
        {
            uint debugBase = BlocksX * BlocksY;
            MotionOut.Store(debugBase * 4u, CandidateCost[0]);
            MotionOut.Store((debugBase + 1u) * 4u, CandidateCost[9]);
        }
    }
}
