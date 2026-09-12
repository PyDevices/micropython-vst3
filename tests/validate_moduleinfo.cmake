# Run the scanner the way a user does, then hold its output against the live
# factory with Steinberg's own tool.
#
# This is the test that catches a moduleinfo which disagrees with the binary,
# and it exists because that already happened: the scan wrote a file that
# omitted the four compiled-in classes, so a host reading the file - which is
# the whole reason the file exists - could not see the developer-loop plug-in
# at all. Nothing in the suite noticed, because everything else asks the
# factory directly and the factory was right.
#
# -validate loads the module and compares every class, field by field, so it
# fails on a missing class, a renamed one, or a vendor string that drifted.

execute_process(
    COMMAND "${MPVST_ENGINE}" mpvst_scan_plugins.py
    WORKING_DIRECTORY "${MPVST_BUNDLE_BIN}"
    RESULT_VARIABLE scan_status
    OUTPUT_VARIABLE scan_output
    ERROR_VARIABLE scan_output)
if(NOT scan_status EQUAL 0)
    message(FATAL_ERROR "mpvst_scan_plugins.py failed (${scan_status}):\n${scan_output}")
endif()
message(STATUS "${scan_output}")

# The bundle path arrives with a "/../.." tail, and the module loader builds
# the library name from the path's last component - which would be "..".
get_filename_component(MPVST_BUNDLE "${MPVST_BUNDLE}" REALPATH)

execute_process(
    COMMAND "${MPVST_TOOL}" -validate -path "${MPVST_BUNDLE}"
    RESULT_VARIABLE validate_status
    OUTPUT_VARIABLE validate_output
    ERROR_VARIABLE validate_output)
if(NOT validate_status EQUAL 0)
    message(FATAL_ERROR
        "moduleinfo.json disagrees with the factory:\n${validate_output}")
endif()

# catalog.json is ours rather than Steinberg's, so no tool validates it. What
# can go wrong is drift: a class in one file and not the other, or the same
# class carrying two different class IDs, which would send a generated project
# at a plug-in that is not there.
execute_process(
    COMMAND "${MPVST_ENGINE}" mpvst_catalog.py
    WORKING_DIRECTORY "${MPVST_BUNDLE_BIN}"
    RESULT_VARIABLE catalog_status
    OUTPUT_VARIABLE catalog_output
    ERROR_VARIABLE catalog_output)
if(NOT catalog_status EQUAL 0)
    message(FATAL_ERROR "mpvst_catalog.py failed (${catalog_status}):\n${catalog_output}")
endif()
message(STATUS "${catalog_output}")

file(READ "${MPVST_BUNDLE_BIN}/../Resources/catalog.json" catalog_text)
file(READ "${MPVST_BUNDLE_BIN}/../Resources/moduleinfo.json" moduleinfo_text)
string(JSON catalog_count LENGTH "${catalog_text}" classes)
math(EXPR checked "0")
foreach(index RANGE 1 ${catalog_count})
    math(EXPR at "${index} - 1")
    string(JSON entry GET "${catalog_text}" classes ${at})
    string(JSON entry_cid GET "${entry}" cid)
    string(JSON entry_name GET "${entry}" name)
    string(FIND "${moduleinfo_text}" "\"CID\": \"${entry_cid}\"" found)
    if(found EQUAL -1)
        message(FATAL_ERROR
            "catalog.json lists ${entry_name} with CID ${entry_cid}, which is "
            "not in moduleinfo.json - a project generated from the catalog "
            "would name a class the host cannot find.")
    endif()
    math(EXPR checked "${checked} + 1")
endforeach()
message(STATUS "catalog.json: ${checked} class IDs all present in moduleinfo.json")
