import sys

import vstaudio


def main():
    vstaudio.configure(sys.argv[1], int(sys.argv[2]))
    script_path = sys.argv[3]

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
