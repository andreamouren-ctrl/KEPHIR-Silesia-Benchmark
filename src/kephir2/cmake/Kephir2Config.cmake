# Kephir2Config.cmake - relocatable integration config for the frozen KEPHIR2 C ABI.
#
# Expected SDK layout:
#   include/kephir2/kephir2_c.h
#   bin/kephir2_api.dll              (Windows)
#   lib/kephir2_api.lib              (Windows)
#   lib/libkephir2_api.so            (Linux, when packaged)
#   cmake/Kephir2Config.cmake

if(TARGET Kephir2::kephir2)
    return()
endif()

get_filename_component(_KEPHIR2_PREFIX "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

add_library(Kephir2::kephir2 SHARED IMPORTED GLOBAL)
set_target_properties(Kephir2::kephir2 PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${_KEPHIR2_PREFIX}/include"
)

if(WIN32)
    set_target_properties(Kephir2::kephir2 PROPERTIES
        IMPORTED_LOCATION "${_KEPHIR2_PREFIX}/bin/kephir2_api.dll"
        IMPORTED_IMPLIB "${_KEPHIR2_PREFIX}/lib/kephir2_api.lib"
    )
elseif(UNIX)
    set_target_properties(Kephir2::kephir2 PROPERTIES
        IMPORTED_LOCATION "${_KEPHIR2_PREFIX}/lib/libkephir2_api.so"
    )
else()
    message(FATAL_ERROR "Kephir2 SDK: unsupported platform")
endif()

set(Kephir2_VERSION "2.0.0-rc1")
set(Kephir2_API_VERSION "1")
set(Kephir2_AUR_CONTAINER_VERSION "2.0")
set(Kephir2_FOUND TRUE)

unset(_KEPHIR2_PREFIX)
