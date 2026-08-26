import sys

import vstaudio


def main():
    vstaudio.configure(sys.argv[1], int(sys.argv[2]))
    script_path = sys.argv[3]

    # The bundle ships a shared script library next to this bootstrap
    # (lib/effects, ...); make it importable for every instance script.
    #
    # Insert it FIRST, and drop the current-directory entries MicroPython
    # puts on sys.path by default. The sidecar inherits its working
    # directory from the DAW, and on a case-insensitive filesystem
    # whatever happens to live there can shadow the library: a portable
    # REAPER install keeps its JSFX in <install>/Effects, which "import
    # effects" happily resolved to - a bare directory, no __init__.py, so
    # every name lookup on the package failed with err=1.
    sys.path[:] = [entry for entry in sys.path if entry not in ("", ".")]
    bootstrap = sys.argv[0].replace("\\", "/")
    slash = bootstrap.rfind("/")
    if slash >= 0:
        sys.path.insert(0, bootstrap[:slash] + "/lib")

    def load_script():
        vstaudio.clear_output()
        try:
            namespace = {"__name__": "__main__", "__file__": script_path}
            with open(script_path, "rb") as script_file:
                source = script_file.read()
            exec(compile(source, script_path, "exec"), namespace, namespace)
        except Exception as exc:
            vstaudio.error("{}: {}".format(type(exc).__name__, exc))
            return False
        vstaudio.error("")
        return True

    load_script()
    vstaudio.run(load_script)


main()
