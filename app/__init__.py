"""Package entry points for the H56 PayPal submission.

Everything that is specific to this submission lives here, never inside `h56_core/`:
that directory is a byte-pinned copy and is checked as an exact file set.

Importing this package must not read the kernel. The kernel imports live inside the
functions that need them, so argument parsing and `--help` stay free of a 110-file read.
"""
import sys

# h56_core is verified as an exact set of files and directories, so a stray
# __pycache__ there does not merely look untidy: it makes the native import refuse the
# tree. `-B` is the contract, and this line extends it to everything imported after this
# module, including a caller that forgot the flag.
sys.dont_write_bytecode = True

__all__ = ["main"]
