cmake_minimum_required(VERSION 3.20)
project(kephir2_core LANGUAGES CXX)

find_package(Python3 REQUIRED COMPONENTS Interpreter)

file(GLOB KEPHIR37_SOURCE_PARTS CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/../../engine/source_parts/src_gz_*.b64"
)

set(KEPHIR37_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(KEPHIR37_GENERATED_CPP "${KEPHIR37_GENERATED_DIR}/kephir37_native.cpp")

add_custom_command(
    OUTPUT "${KEPHIR37_GENERATED_CPP}"
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${KEPHIR37_GENERATED_DIR}"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/backend/generate_native37.py"
            --output "${KEPHIR37_GENERATED_CPP}"
    DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/backend/generate_native37.py"
        ${KEPHIR37_SOURCE_PARTS}
        "${CMAKE_CURRENT_SOURCE_DIR}/../../research/generators/general/make_exp26_source.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../research/generators/general/make_exp27_source.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../research/generators/general/make_exp31_source.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../research/generators/general/make_exp33_source.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../research/generators/general/make_exp37_source.py"
    VERBATIM
)

add_library(kephir37_native STATIC
    "${KEPHIR37_GENERATED_CPP}"
)
target_include_directories(kephir37_native
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_compile_features(kephir37_native PUBLIC cxx_std_20)
target_compile_definitions(kephir37_native PRIVATE
    NO_INTERNAL_VERIFY
    K2_ADAPT_MODE=9
    K2_LAZY_MODE=1
    K2_PSG_MODE=3
    K2_DIST_TOPO_MODE=8
    K2_DUAL_MATCH_MODE=1
)
set_target_properties(kephir37_native PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(kephir2_core STATIC
    src/analyzer.cpp
    src/auto_routing.cpp
    src/archive.cpp
    src/execution.cpp
    src/native37_blob.cpp
    src/native_k75.cpp
    src/packing.cpp
    src/planner.cpp
    src/strategy.cpp
)

target_include_directories(kephir2_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(kephir2_core PUBLIC cxx_std_20)
target_link_libraries(kephir2_core PUBLIC kephir37_native)
set_target_properties(kephir2_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

if (MSVC)
    target_compile_options(kephir2_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(kephir2_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(kephir2_strategy_smoke
    tests/strategy_smoke.cpp
)
target_link_libraries(kephir2_strategy_smoke PRIVATE kephir2_core)

add_executable(kephir2_analyzer_smoke
    tests/analyzer_smoke.cpp
)
target_link_libraries(kephir2_analyzer_smoke PRIVATE kephir2_core)

add_executable(kephir2_analyzer_dump
    tests/analyzer_dump.cpp
)
target_link_libraries(kephir2_analyzer_dump PRIVATE kephir2_core)

add_executable(kephir2_planner_smoke
    tests/planner_smoke.cpp
)
target_link_libraries(kephir2_planner_smoke PRIVATE kephir2_core)

add_executable(kephir2_planner_dump
    tests/planner_dump.cpp
)
target_link_libraries(kephir2_planner_dump PRIVATE kephir2_core)

add_executable(kephir2_archive_smoke
    tests/archive_smoke.cpp
)
target_link_libraries(kephir2_archive_smoke PRIVATE kephir2_core)

add_executable(kephir2_archive_dump
    tests/archive_dump.cpp
)
target_link_libraries(kephir2_archive_dump PRIVATE kephir2_core)

add_executable(kephir2_packing_smoke
    tests/packing_smoke.cpp
)
target_link_libraries(kephir2_packing_smoke PRIVATE kephir2_core)

add_executable(kephir2_packing_dump
    tests/packing_dump.cpp
)
target_link_libraries(kephir2_packing_dump PRIVATE kephir2_core)

add_executable(kephir2_execution_smoke
    tests/execution_smoke.cpp
)
target_link_libraries(kephir2_execution_smoke PRIVATE kephir2_core)

add_executable(kephir2_native37_smoke
    tests/native37_smoke.cpp
)
target_link_libraries(kephir2_native37_smoke PRIVATE kephir37_native)

add_executable(kephir2_native37_blob_smoke
    tests/native37_blob_smoke.cpp
)
target_link_libraries(kephir2_native37_blob_smoke PRIVATE kephir2_core)

add_executable(kephir2_native_k75_smoke
    tests/native_k75_smoke.cpp
)
target_link_libraries(kephir2_native_k75_smoke PRIVATE kephir2_core)

add_executable(kephir2_interop_tool
    tests/interop_tool.cpp
)
target_link_libraries(kephir2_interop_tool PRIVATE kephir2_core)

add_executable(kephir2_native_k75_cli
    tests/native_k75_cli.cpp
)
target_link_libraries(kephir2_native_k75_cli PRIVATE kephir2_core)

add_executable(kephir2_auto_routing_smoke
    tests/auto_routing_smoke.cpp
)
target_link_libraries(kephir2_auto_routing_smoke PRIVATE kephir2_core)

add_executable(kephir2_production_layout_bench
    tests/production_layout_bench.cpp
)
target_link_libraries(kephir2_production_layout_bench PRIVATE kephir2_core)

enable_testing()
add_test(NAME kephir2_strategy_smoke COMMAND kephir2_strategy_smoke)
add_test(NAME kephir2_analyzer_smoke COMMAND kephir2_analyzer_smoke)
add_test(NAME kephir2_planner_smoke COMMAND kephir2_planner_smoke)
add_test(NAME kephir2_archive_smoke COMMAND kephir2_archive_smoke)
add_test(NAME kephir2_packing_smoke COMMAND kephir2_packing_smoke)
add_test(NAME kephir2_execution_smoke COMMAND kephir2_execution_smoke)
add_test(NAME kephir2_native37_smoke COMMAND kephir2_native37_smoke)
add_test(NAME kephir2_native37_blob_smoke COMMAND kephir2_native37_blob_smoke)
add_test(NAME kephir2_native_k75_smoke COMMAND kephir2_native_k75_smoke)
add_test(NAME kephir2_auto_routing_smoke COMMAND kephir2_auto_routing_smoke)


add_library(kephir2_api SHARED
    src/kephir2_c.cpp
)
target_include_directories(kephir2_api
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_compile_features(kephir2_api PUBLIC cxx_std_20)
target_compile_definitions(kephir2_api PRIVATE KEPHIR2_BUILD_DLL=1)
target_link_libraries(kephir2_api PRIVATE kephir2_core)

add_executable(kephir2_api_smoke
    tests/api_smoke.cpp
)
target_link_libraries(kephir2_api_smoke PRIVATE kephir2_api)
add_test(NAME kephir2_api_smoke COMMAND kephir2_api_smoke)
