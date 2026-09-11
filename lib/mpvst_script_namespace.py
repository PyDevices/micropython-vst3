"""Where a bare script's declarations are left for the panel to find.

A script is exec'd into a dict rather than imported, so there is no module for
anything to look its `MACRO_LABELS` up in. The bootstrap leaves the namespace
here on its way past and the panel reads it from here.

A module of its own rather than an attribute on the bootstrap, because the
bootstrap is the process's main script and calls `main()` at the bottom:
importing it to read one name would start a second sidecar inside the first.
"""

namespace = None
