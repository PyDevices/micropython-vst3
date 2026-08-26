# Stage lib/ into the plug-in bundle, without Python's bytecode cache.
#
# Run with -P at build time, so a newly added script is picked up without
# reconfiguring:
#
#   cmake -DMPVST_LIB_SRC=<repo>/lib -DMPVST_LIB_DST=<bundle>/lib
#         -P plugin/stage_lib.cmake
#
# cmake -E copy_directory has no exclude filter, so it dragged every
# __pycache__/*.pyc a local test run happened to leave behind into the
# shipped bundle - including stale files compiled by a different Python
# version than the engine runs. They are never read (the engine imports
# from source) and are pure noise in a release archive.
#
# The destination is cleared first rather than filtered afterwards. That
# keeps it an exact mirror of the source - a script deleted or renamed in
# lib/ does not linger in the bundle - and it avoids needing to hunt for
# stale caches at all. Do not try to prune them with
# file(GLOB_RECURSE ... LIST_DIRECTORIES true): that returns every
# directory it walks through regardless of the pattern, so a glob meant to
# match only __pycache__ happily matches lib/effects and lib/instruments
# as well.

if(NOT DEFINED MPVST_LIB_SRC OR NOT DEFINED MPVST_LIB_DST)
    message(FATAL_ERROR "MPVST_LIB_SRC and MPVST_LIB_DST are required")
endif()

file(REMOVE_RECURSE "${MPVST_LIB_DST}")

file(GLOB_RECURSE entries RELATIVE "${MPVST_LIB_SRC}" "${MPVST_LIB_SRC}/*")
foreach(entry IN LISTS entries)
    if(entry MATCHES "(^|/)__pycache__/" OR entry MATCHES "\\.pyc$")
        continue()
    endif()
    # COPYONLY creates missing parent directories on the way.
    configure_file("${MPVST_LIB_SRC}/${entry}" "${MPVST_LIB_DST}/${entry}"
                   COPYONLY)
endforeach()
