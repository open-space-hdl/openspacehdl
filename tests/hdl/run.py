"""Unit benches of the bench components of openspacehdl (library osh_tb), VUnit with GHDL.

    python tests/hdl/run.py [VUnit options]      for example: python tests/hdl/run.py -p 2 -o <output dir>

Needs an installation of openspacehdl with its source snapshots (a wheel built by tools/check.py --real-build) and
VUnit; a wheel built with waived rules also needs OPENSPACEHDL_ALLOW_WAIVED=1. tests/test_osh_tb_hdl.py runs this
file when OPENSPACEHDL_HDL_TESTS=1.
"""

import os
from pathlib import Path

os.environ.setdefault("VUNIT_SIMULATOR", "ghdl")

from vunit import VUnit  # noqa: E402  (import after the simulator selection)

import openspacehdl as osh  # noqa: E402
from openspacehdl.vunit import RELAXED_GHDL_FLAGS  # noqa: E402

HERE = Path(__file__).resolve().parent

osh.guard_ghdl_generics()
try:
    vu = VUnit.from_argv(compile_builtins=False)
except TypeError:  # VUnit 5 has no compile_builtins
    vu = VUnit.from_argv()
vu.add_vhdl_builtins()
osh.add_osh_tb(vu)
lib = vu.add_library("osh_tb_test", vhdl_standard="2008")
for f in sorted(HERE.glob("*.vhd")):
    lib.add_source_file(str(f), vhdl_standard="2008").add_compile_option("ghdl.a_flags", list(RELAXED_GHDL_FLAGS))

# The SpaceFibre far end with one and four lanes, the RMAP target on virtual channel 0 and 1
for lanes, vc in ((1, 1), (4, 0)):
    lib.test_bench("osh_tb_spfi_far_end_tb").add_config(f"lanes{lanes}_vc{vc}",
                                                        generics={"NumLanes_g": lanes, "RmapVc_g": vc})

# UVVM needs -frelaxed at elaboration in GHDL; large arrays need an unlimited stack
vu.set_sim_option("ghdl.elab_flags", ["-frelaxed"])
vu.set_sim_option("ghdl.sim_flags", ["--max-stack-alloc=0"])
vu.set_sim_option("disable_ieee_warnings", True)
vu.main()
