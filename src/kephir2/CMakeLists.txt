cmake_minimum_required(VERSION 3.20)
project(kephir2_core LANGUAGES CXX)

add_library(kephir2_core STATIC
    src/analyzer.cpp
    src/archive.cpp
    src/packing.cpp
    src/planner.cpp
    src/strategy.cpp
)

target_include_directories(kephir2_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(kephir2_core PUBLIC cxx_std_20)

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

enable_testing()
add_test(NAME kephir2_strategy_smoke COMMAND kephir2_strategy_smoke)
add_test(NAME kephir2_analyzer_smoke COMMAND kephir2_analyzer_smoke)
add_test(NAME kephir2_planner_smoke COMMAND kephir2_planner_smoke)
add_test(NAME kephir2_archive_smoke COMMAND kephir2_archive_smoke)
add_test(NAME kephir2_packing_smoke COMMAND kephir2_packing_smoke)


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
