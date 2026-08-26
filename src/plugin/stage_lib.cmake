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

# Clear only the entries this source root owns. The destination is the
# bundle directory itself, which also holds the plug-in binary and the
# engine, so wiping all of it would delete the build. Two invocations
# stage into the same bundle - this repository's lib/ and audioif's - so
# neither may touch what it did not put there.
#
# What it staged last time is recorded beside the bundle, which is what
# lets a top-level entry *deleted* from the source be removed as well.
# Without that record a deleted package would sit in the bundle forever:
# the glob below only sees what still exists, so it could clear what it
# was about to rewrite but never what had gone away. That mattered when
# effects/ and midi_cc.py moved out to audioif - the plug-in kept loading
# a stale copy of both, and the bootstrap's docstring has the story of
# what a stray bare directory on sys.path does to an import.
#
# Do not reach for file(GLOB_RECURSE ... LIST_DIRECTORIES true) to hunt
# stale caches instead: it returns every directory it walks regardless of
# the pattern, so a glob written to match only __pycache__ also matches
# effects/ and instruments/.
get_filename_component(mpvst_stage_name "${MPVST_LIB_SRC}" ABSOLUTE)
string(MD5 mpvst_stage_id "${mpvst_stage_name}")
set(mpvst_stamp "${MPVST_LIB_DST}/.staged-${mpvst_stage_id}")

file(GLOB top_level RELATIVE "${MPVST_LIB_SRC}" "${MPVST_LIB_SRC}/*")
if(EXISTS "${mpvst_stamp}")
    file(STRINGS "${mpvst_stamp}" mpvst_previous)
else()
    set(mpvst_previous "")
endif()
foreach(entry IN LISTS top_level mpvst_previous)
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

# An empty source directory - a package whose files are gone but whose
# __pycache__ keeps it alive - stages nothing, so record only what
# actually landed. Otherwise the stamp would list a directory that is not
# there and the next run would report nothing to remove.
set(mpvst_staged "")
foreach(entry IN LISTS top_level)
    if(EXISTS "${MPVST_LIB_DST}/${entry}")
        list(APPEND mpvst_staged "${entry}")
    endif()
endforeach()
string(REPLACE ";" "\n" mpvst_staged "${mpvst_staged}")
file(WRITE "${mpvst_stamp}" "${mpvst_staged}\n")
