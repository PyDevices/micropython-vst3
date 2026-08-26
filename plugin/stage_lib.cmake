# Stage the contents of lib/ beside the engine binary, without Python's
# bytecode cache.
#
# Run with -P at build time, so a newly added script is picked up without
# reconfiguring:
#
#   cmake -DMPVST_LIB_SRC=<repo>/lib -DMPVST_LIB_DST=<bundle dir>
#         -P plugin/stage_lib.cmake
#
# lib/'s *contents* land at the destination, not a lib/ subdirectory: the
# bootstrap puts its own directory on sys.path, so effects/, instruments/
# and the bootstrap itself all sit together next to the engine.
#
# cmake -E copy_directory has no exclude filter, so it dragged every
# __pycache__/*.pyc a local test run happened to leave behind into the
# shipped bundle - including stale files compiled by a different Python
# version than the engine runs. They are never read (the engine imports
# from source) and are pure noise in a release archive.

if(NOT DEFINED MPVST_LIB_SRC OR NOT DEFINED MPVST_LIB_DST)
    message(FATAL_ERROR "MPVST_LIB_SRC and MPVST_LIB_DST are required")
endif()

# Clear only the entries lib/ owns. The destination is the bundle
# directory itself, which also holds the plug-in binary and the engine, so
# wiping all of it would delete the build. Removing each top-level entry
# means a renamed or deleted script inside effects/ or instruments/ cannot
# linger; a top-level entry deleted from lib/ outright is the one case
# that would need a clean build.
#
# Do not reach for file(GLOB_RECURSE ... LIST_DIRECTORIES true) to hunt
# stale caches instead: it returns every directory it walks regardless of
# the pattern, so a glob written to match only __pycache__ also matches
# effects/ and instruments/.
file(GLOB top_level RELATIVE "${MPVST_LIB_SRC}" "${MPVST_LIB_SRC}/*")
foreach(entry IN LISTS top_level)
    file(REMOVE_RECURSE "${MPVST_LIB_DST}/${entry}")
endforeach()

file(GLOB_RECURSE entries RELATIVE "${MPVST_LIB_SRC}" "${MPVST_LIB_SRC}/*")
foreach(entry IN LISTS entries)
    if(entry MATCHES "(^|/)__pycache__/" OR entry MATCHES "\\.pyc$")
        continue()
    endif()
    # COPYONLY creates missing parent directories on the way.
    configure_file("${MPVST_LIB_SRC}/${entry}" "${MPVST_LIB_DST}/${entry}"
                   COPYONLY)
endforeach()
