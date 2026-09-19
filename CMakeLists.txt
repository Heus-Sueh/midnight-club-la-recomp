# midnight_club_la - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(midnight_club_la LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(MCLA_ENABLE_HOTSPOT_PROBE
    "Instrument selected guest functions for performance investigation" OFF)
option(MCLA_BUILD_TESTS "Build project-owned native renderer tests" OFF)

include(generated/rexglue.cmake)

# Sources
set(MIDNIGHTCLUBLA_SOURCES
    src/main.cpp
    src/native_renderer/native_renderer.cpp
    src/native_renderer/native_pass_batch.cpp
    src/native_renderer/native_scene.cpp
    src/native_renderer/camera_interpolator.cpp
)

if(MCLA_ENABLE_HOTSPOT_PROBE)
    list(APPEND MIDNIGHTCLUBLA_SOURCES src/hotspot_probe.cpp)
endif()

if(WIN32)
    add_executable(midnight_club_la WIN32 ${MIDNIGHTCLUBLA_SOURCES})
else()
    add_executable(midnight_club_la ${MIDNIGHTCLUBLA_SOURCES})
endif()

target_include_directories(midnight_club_la PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}"
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
)

if(MCLA_ENABLE_HOTSPOT_PROBE)
    target_compile_definitions(midnight_club_la PRIVATE MCLA_ENABLE_HOTSPOT_PROBE=1)
endif()

# ReXGlue v0.10.0 compiles rex_app.cpp into the host but does not propagate
# Dear ImGui's include directory through rex::runtime. Keep this source-tree
# workaround local to the pinned SDK version.
if(REXSDK_DIR)
    target_include_directories(midnight_club_la PRIVATE
        "${REXSDK_DIR}/thirdparty/imgui")
endif()

rexglue_setup_target(midnight_club_la GPU_PLUGINS xenos)

if(MCLA_BUILD_TESTS)
    enable_testing()
    add_executable(mcla_native_pass_batch_test
        tests/native_pass_batch_test.cpp
        src/native_renderer/native_pass_batch.cpp
    )
    target_include_directories(mcla_native_pass_batch_test PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
    )
    add_test(NAME native_pass_batch COMMAND mcla_native_pass_batch_test)
endif()

# The runtime resolves its default configuration beside the executable. Keep
# that staged copy synchronized on every link so local tuning, packaged builds,
# and Windows/Linux runs all consume the same checked-in settings.
add_custom_command(TARGET midnight_club_la POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/midnight_club_la.toml"
        "$<TARGET_FILE_DIR:midnight_club_la>/midnight_club_la.toml"
    VERBATIM)

# The v0.10.0 helper sets an $ORIGIN RPATH on Linux, but only stages shared
# runtime libraries automatically on Windows and macOS. Put the Linux runtime
# beside the executable as well so the build tree is directly runnable.
if(UNIX AND NOT APPLE)
    foreach(runtime_target rex::runtime TracyClient)
        if(TARGET ${runtime_target})
            add_custom_command(TARGET midnight_club_la POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy_if_different
                    $<TARGET_FILE:${runtime_target}>
                    $<TARGET_FILE_DIR:midnight_club_la>
                VERBATIM)
        endif()
    endforeach()
endif()
