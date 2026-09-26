#pragma once

#include <array>
#include <cstdint>
#include <string_view>

namespace kephir2::factory_grain {

struct Rule {
    std::string_view key;
    std::uint32_t grain;
    std::uint32_t trials;
    std::uint32_t wins;
    std::int64_t gain;
};

inline constexpr std::array<Rule, 72> kRules{{
    Rule{"l1:h1:z4:p0:s4", 262144u, 6u, 6u, 2610},
    Rule{"l1:h1:z4:p0:s4", 513216u, 6u, 6u, 4170},
    Rule{"l1:h3:z4:p0:s0", 131072u, 3u, 3u, 4038},
    Rule{"l1:h5:z0:p4:s7", 262144u, 3u, 3u, 4800},
    Rule{"l1:h5:z0:p4:s7", 335746u, 3u, 3u, 2811},
    Rule{"l1:h5:z3:p1:s1", 364544u, 3u, 3u, 26223},
    Rule{"l2:h3:z4:p0:s0", 131072u, 3u, 3u, 6243},
    Rule{"l2:h3:z4:p0:s0", 262144u, 3u, 3u, 5484},
    Rule{"l2:h4:z2:p0:s7", 262144u, 3u, 3u, 1917},
    Rule{"l2:h4:z2:p0:s7", 524288u, 3u, 3u, 1569},
    Rule{"l2:h4:z3:p1:s2", 524288u, 3u, 3u, 3390},
    Rule{"l2:h5:z0:p0:s2", 524288u, 3u, 3u, 18198},
    Rule{"l2:h5:z0:p4:s1", 524288u, 33u, 33u, 131448},
    Rule{"l2:h5:z0:p4:s2", 524288u, 18u, 15u, 74055},
    Rule{"l2:h5:z0:p4:s3", 262144u, 9u, 9u, 24699},
    Rule{"l2:h5:z0:p4:s3", 524288u, 9u, 9u, 35751},
    Rule{"l2:h5:z0:p4:s5", 262144u, 3u, 3u, 6819},
    Rule{"l2:h5:z0:p4:s7", 262144u, 3u, 3u, 20271},
    Rule{"l2:h5:z0:p4:s7", 524288u, 3u, 3u, 37281},
    Rule{"l2:h5:z1:p1:s1", 524288u, 9u, 9u, 45516},
    Rule{"l2:h5:z1:p1:s2", 524288u, 6u, 6u, 25878},
    Rule{"l2:h5:z1:p1:s3", 262144u, 6u, 6u, 21846},
    Rule{"l2:h5:z1:p1:s3", 524288u, 6u, 6u, 47895},
    Rule{"l2:h5:z1:p1:s6", 262144u, 3u, 3u, 9654},
    Rule{"l2:h5:z1:p1:s6", 524288u, 3u, 3u, 13044},
    Rule{"l2:h5:z1:p3:s3", 262144u, 3u, 3u, 2412},
    Rule{"l2:h5:z1:p4:s2", 524288u, 6u, 6u, 16146},
    Rule{"l2:h5:z1:p4:s3", 262144u, 3u, 3u, 25686},
    Rule{"l2:h5:z1:p4:s3", 524288u, 3u, 3u, 34155},
    Rule{"l2:h5:z2:p1:s2", 524288u, 3u, 3u, 12837},
    Rule{"l2:h5:z2:p1:s3", 262144u, 6u, 6u, 35262},
    Rule{"l2:h5:z2:p1:s3", 524288u, 6u, 6u, 54291},
    Rule{"l2:h5:z2:p1:s7", 524288u, 3u, 3u, 1191},
    Rule{"l2:h5:z2:p2:s7", 524288u, 3u, 3u, 16635},
    Rule{"l2:h5:z2:p3:s3", 262144u, 3u, 3u, 9618},
    Rule{"l2:h5:z2:p3:s3", 524288u, 3u, 3u, 10800},
    Rule{"l2:h5:z2:p3:s4", 262144u, 3u, 3u, 43968},
    Rule{"l2:h5:z2:p3:s4", 524288u, 3u, 3u, 81159},
    Rule{"l2:h6:z0:p1:s1", 524288u, 3u, 3u, 4131},
    Rule{"l2:h6:z0:p3:s7", 262144u, 9u, 9u, 30333},
    Rule{"l2:h6:z0:p4:s7", 262144u, 3u, 3u, 28512},
    Rule{"l2:h6:z0:p4:s7", 524288u, 3u, 3u, 36300},
    Rule{"l2:h6:z1:p1:s1", 524288u, 12u, 12u, 45228},
    Rule{"l2:h6:z1:p1:s2", 524288u, 24u, 24u, 99591},
    Rule{"l2:h6:z1:p1:s3", 262144u, 9u, 9u, 42192},
    Rule{"l2:h6:z1:p1:s3", 524288u, 9u, 9u, 100632},
    Rule{"l2:h6:z1:p1:s4", 262144u, 15u, 12u, 38991},
    Rule{"l2:h6:z1:p1:s4", 524288u, 15u, 15u, 167403},
    Rule{"l2:h6:z1:p1:s6", 262144u, 3u, 3u, 9255},
    Rule{"l2:h6:z1:p1:s6", 524288u, 3u, 3u, 8628},
    Rule{"l2:h6:z1:p2:s1", 524288u, 3u, 3u, 5205},
    Rule{"l2:h6:z1:p2:s2", 524288u, 9u, 9u, 24405},
    Rule{"l2:h6:z1:p2:s3", 262144u, 15u, 12u, 19425},
    Rule{"l2:h6:z1:p2:s4", 262144u, 15u, 15u, 33501},
    Rule{"l2:h6:z1:p2:s4", 524288u, 15u, 15u, 55737},
    Rule{"l2:h6:z1:p3:s7", 262144u, 3u, 3u, 4287},
    Rule{"l2:h6:z1:p3:s7", 524288u, 3u, 3u, 22389},
    Rule{"l2:h6:z2:p1:s1", 524288u, 3u, 3u, 8931},
    Rule{"l2:h6:z2:p1:s3", 262144u, 6u, 6u, 10992},
    Rule{"l2:h6:z2:p1:s4", 262144u, 3u, 3u, 12000},
    Rule{"l2:h6:z2:p1:s4", 524288u, 3u, 3u, 16455},
    Rule{"l2:h6:z2:p2:s3", 524288u, 3u, 3u, 14901},
    Rule{"l2:h7:z0:p1:s3", 262144u, 3u, 3u, 17652},
    Rule{"l2:h7:z0:p1:s3", 524288u, 3u, 3u, 23328},
    Rule{"l2:h7:z0:p1:s5", 262144u, 3u, 3u, 18333},
    Rule{"l2:h7:z0:p1:s5", 524288u, 3u, 3u, 48141},
    Rule{"l2:h7:z0:p2:s3", 262144u, 3u, 3u, 37425},
    Rule{"l2:h7:z0:p2:s3", 524288u, 3u, 3u, 49881},
    Rule{"l2:h7:z0:p3:s7", 262144u, 3u, 3u, 2826},
    Rule{"l2:h7:z0:p3:s7", 524288u, 3u, 3u, 46158},
    Rule{"l2:h7:z1:p1:s7", 524288u, 3u, 3u, 26553},
    Rule{"l2:h7:z1:p2:s2", 524288u, 3u, 3u, 34074},
}};

} // namespace kephir2::factory_grain
