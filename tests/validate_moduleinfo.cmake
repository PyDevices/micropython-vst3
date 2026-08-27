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
    COMMAND "${MPVST_ENGINE}" scan_plugins.py --write
    WORKING_DIRECTORY "${MPVST_BUNDLE_BIN}"
    RESULT_VARIABLE scan_status
    OUTPUT_VARIABLE scan_output
    ERROR_VARIABLE scan_output)
if(NOT scan_status EQUAL 0)
    message(FATAL_ERROR "scan_plugins.py failed (${scan_status}):\n${scan_output}")
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
