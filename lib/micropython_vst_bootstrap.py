import sys

import vstaudio


def main():
    vstaudio.configure(sys.argv[1], int(sys.argv[2]))
    script_path = sys.argv[3]
    # The plug-in names the editor's shared mapping in a fourth argument when
    # it managed to create one. Its absence is the whole compatibility story
    # for the editor: an engine built before it, or a plug-in that could not
    # allocate the region, simply renders audio with no editor.
    ui_mapping = sys.argv[4] if len(sys.argv) > 4 else None

    # The shared script library (effects/, instruments/, ...) ships beside
    # this bootstrap; make it importable for every instance script.
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
        sys.path.insert(0, bootstrap[:slash])

    editor = None
    if ui_mapping:
        try:
            import vst_editor

            editor = vst_editor.start(ui_mapping, script_path)
        except Exception as exc:
            # An editor that will not even start must not stop the instance
            # from playing. The failure is reported the same way a script
            # error is, and rendering continues.
            sys.print_exception(exc)
            editor = None

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

    def reload_script():
        # The editor is told after the load either way, so a script that
        # failed still gets a panel describing what is actually running.
        loaded = load_script()
        if editor is not None:
            editor.script_reloaded(script_path)
        return loaded

    load_script()
    try:
        vstaudio.run(reload_script, editor.tick if editor is not None else None)
    finally:
        if editor is not None:
            editor.stop()


main()
