"""Tests of the plan of the generated testbench (openspacehdl.bench) and of the generated texts that use it."""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from openspacehdl import bench, composer, generate, lock, project

FIX = Path(__file__).resolve().parent / "fixtures" / "composer"
SCHEMAS = FIX / "schema"
SPW = FIX / "spw_rmap_node" / "spw_rmap_node.composer.json"
SPFI = FIX / "spacefibre_node" / "spacefibre_node.composer.json"


def make_lock(example: Path):
    """A lock manifest with the pins of an example."""
    data = json.loads(example.read_text(encoding="utf-8"))
    entity = data["resolved"]["entity"]
    cores, olo = [], None
    for c in data["resolved"]["compile"]:
        if c["library"] == "olo":
            olo = c
        elif c["library"] != entity:
            cores.append({"id": c["library"], "name": c["library"], "repository": f"open-space-hdl/{c['source']}",
                          "tag": "v0.1.0", "commit": c["commit"], "library": c["library"],
                          "fileList": "compile_order.txt", "fileListFormat": "files", "models": {}})
    return lock.Lock.from_dict({
        "format": "openspacehdl-lock", "version": 1, "package": "0.1.0",
        "website": {"commit": "7" * 40, "catalog": "x", "generator": "0.9.8-beta"},
        "referenceSystems": {"tag": "v0.1.1", "commit": "4" * 40},
        "openLogic": {"tag": olo["tag"], "commit": olo["commit"], "library": "olo", "fileList": "compile_order.txt",
                      "repository": "open-space-hdl/open-logic-ft"},
        "uvvm": {"commit": "5" * 40}, "cores": cores, "files": {},
    })


def load(example: Path, lk=None):
    return composer.load(example, lock=lk or make_lock(example), schema_dir=SCHEMAS)


def variant(tmp_path: Path, example: Path, mutate) -> Path:
    """A changed copy of an example with an export whose header names its SHA-256."""
    data = json.loads(example.read_text(encoding="utf-8"))
    mutate(data)
    d = tmp_path / "variant"
    target = d / example.name
    shutil.copytree(example.parent / "hdl", d / "hdl")
    target.write_text(json.dumps(data, indent=1), encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    order = next((d / "hdl").glob("*_compile_order.txt"))
    order.write_text(re.sub(r"(# SHA-256 of .*: )[0-9a-f]{64}", lambda m: m.group(1) + digest,
                            order.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    return target


def instance(data: dict, iid: str) -> dict:
    return next(i for i in data["resolved"]["instances"] if i["id"] == iid)


def actual(data: dict, iid: str, port: str) -> str:
    return next(p["actual"] for p in instance(data, iid)["ports"] if p["name"] == port)


def test_the_plan_of_a_spacewire_node():
    system = load(SPW)
    p = bench.plan(system)
    labels = {c.label: c for c in p.components}
    assert sorted(labels) == ["i_axi_mem_0", "i_axilite_0", "i_axilite_1", "i_far_end_0"]
    assert labels["i_axilite_0"].endpoint == "spw0.S_AxiLite" and labels["i_axilite_1"].endpoint == "rmap0.S_AxiLite"
    assert dict(labels["i_axilite_0"].generics) == {"Instance_g": "0", "AddrWidth_g": "8"}
    far = labels["i_far_end_0"]
    assert far.entity == "osh_tb_spw_far_end" and p.far_ends == ["spw0.Spw"]
    link, user = actual(system.data, "spw0", "LinkClk"), actual(system.data, "spw0", "UserClk")
    assert dict(far.generics) == {"LinkClkHz_g": bench.hz(link), "ClkHz_g": bench.hz(user), "RunDiv_g": "2"}
    ports = dict(far.ports)
    assert ports["Clk"] == user and ports["LinkClk"] == link and ports["Res"] == "osh_rmap_res(0)"
    sig = {p.signal: p.name for i in system.interfaces if i.endpoint == "spw0.Spw" for p in i.ports}
    assert ports["Spw_DOut"] == sig["d_in"] and ports["Spw_SIn"] == sig["s_out"]
    mem = labels["i_axi_mem_0"]
    assert dict(mem.generics)["SizeBytes_g"] == "16384" and dict(mem.ports)["Rst"] == "osh_rst"
    # The port of spw0 starts neither by LinkStart nor by AutoStart: the smoke test writes PORT_CTRL
    assert [(s.endpoint, s.vvc, s.addr, s.value) for s in p.starts] == [("spw0.Spw", 0, 0x10, 0x38)]
    assert sorted((c.bank, c.via, c.index, c.addr, c.value) for c in p.checks) == [
        ("rmap0.S_AxiLite", "axilite", 1, 0, 'x"4F4D4101"'), ("spw0.S_AxiLite", "axilite", 0, 0, 'x"4F575201"')]
    assert [(m.space, m.far, m.mem, m.tla, m.key, m.addr) for m in p.memory_checks] == [
        ("rmap0.M_Axi", 0, 0, 'x"FE"', 'x"00"', 0x0FFC)]
    assert p.clocks == []


def test_the_plan_of_a_spacefibre_node():
    system = load(SPFI)
    p = bench.plan(system)
    labels = {c.label: c for c in p.components}
    far = labels["i_far_end_0"]
    assert far.entity == "osh_tb_spfi_far_end" and p.far_ends == ["pa0.Gt"]
    sys_clk = actual(system.data, "pa0", "FreeRunClk")
    assert dict(far.generics) == {"NumLanes_g": "1", "NumVc_g": "2", "VcInDepth_g": "256", "RmapVc_g": "0",
                                  "RefClkHz_g": bench.hz("pa0_RefClk"), "SysClkHz_g": bench.hz(sys_clk),
                                  "ModelIdx_g": "1"}
    assert [(c.port, c.hz) for c in p.clocks] == [("pa0_RefClk", 156_250_000)]
    assert dict(far.ports)["RefClk"] == "pa0_RefClk"
    streams = {c.endpoint: c for c in p.components if c.entity.startswith("osh_tb_axis")}
    assert streams["spp0.S_Tx[0]"].entity == "osh_tb_axis_master"
    assert streams["spp0.M_Rx[0]"].entity == "osh_tb_axis_slave"
    assert dict(streams["spp0.S_Tx[0]"].generics) == {"Instance_g": "0", "DataWidth_g": "32", "KeepWidth_g": "4",
                                                     "UserWidth_g": "28"}
    assert p.starts == []
    assert sorted(c.bank for c in p.checks) == ["ofb0.S_AxiLite", "rmap0.S_AxiLite", "spp0.S_AxiLite"]
    assert [(m.far, m.mem) for m in p.memory_checks] == [(0, 0)]


def test_register_banks_behind_an_rmap_target(tmp_path):
    def move_spp_behind_rmap(d):
        spaces = d["resolved"]["addressMap"]
        port = next(s for s in spaces if s["space"] == "spp0.S_AxiLite")
        spaces.remove(port)
        bank = dict(port["banks"][0], base=0x10000)
        next(s for s in spaces if s["space"] == "rmap0.M_Axi")["banks"].append(bank)
        spp = next(b for b in d["catalogSubset"]["blocks"] if b["id"] == "openspp/spp_core")
        spp["idRegister"] = dict(spp["idRegister"], address="0x004")

    p = bench.plan(load(variant(tmp_path, SPFI, move_spp_behind_rmap), make_lock(SPFI)))
    rmap = [c for c in p.checks if c.via == "rmap"]
    assert [(c.bank, c.index, c.addr, c.value, c.tla, c.key) for c in rmap] == [
        ("spp0.S_AxiLite", 0, 0x10004, 'x"53505001"', 'x"FE"', 'x"00"')]


def test_the_rmap_target_on_another_virtual_channel(tmp_path):
    def swap_channels(d):
        for c in d["connections"]:
            for end in ("from", "to"):
                c[end] = {"ofb0.S_Vc[0]": "ofb0.S_Vc[1]", "ofb0.S_Vc[1]": "ofb0.S_Vc[0]",
                          "ofb0.M_Vc[0]": "ofb0.M_Vc[1]", "ofb0.M_Vc[1]": "ofb0.M_Vc[0]"}.get(c[end], c[end])

    p = bench.plan(load(variant(tmp_path, SPFI, swap_channels), make_lock(SPFI)))
    far = next(c for c in p.components if c.label == "i_far_end_0")
    assert dict(far.generics)["RmapVc_g"] == "1"


def test_the_offset_of_the_id_register_and_a_bank_without_one(tmp_path):
    def change_id_registers(d):
        blocks = {b["id"]: b for b in d["catalogSubset"]["blocks"]}
        blocks["openspp/spp_core"]["idRegister"] = dict(blocks["openspp/spp_core"]["idRegister"], address="0x004")
        del blocks["openfibre/ofb_core"]["idRegister"]

    p = bench.plan(load(variant(tmp_path, SPFI, change_id_registers), make_lock(SPFI)))
    checks = {c.bank: c for c in p.checks}
    assert checks["spp0.S_AxiLite"].addr == 4 and checks["spp0.S_AxiLite"].value == 'x"53505001"'
    assert checks["ofb0.S_AxiLite"].addr == 0 and checks["ofb0.S_AxiLite"].value is None
    pkg = generate.harness_package(load(variant(tmp_path / "b", SPFI, change_id_registers), make_lock(SPFI)), "--\n")
    assert 'axilite_read(axilite, 1, to_unsigned(16#0#, 12),' in pkg
    assert 'axilite_check(axilite, 2, to_unsigned(16#4#, 11), x"53505001",' in pkg


def refused(tmp_path, example, mutate, match):
    with pytest.raises(bench.BenchError, match=match):
        bench.plan(load(variant(tmp_path, example, mutate), make_lock(example)))


def test_an_axi4_slave_is_refused(tmp_path):
    def slave(d):
        block = next(b for b in d["catalogSubset"]["blocks"] if b["id"] == "openrmap/omap_core")
        next(i for i in block["interfaces"] if i["name"] == "M_Axi")["role"] = "slave"

    refused(tmp_path, SPW, slave, r"rmap0\.M_Axi is an AXI4 slave.*a later version adds the UVVM AXI4 VVC")


def test_an_rmap_target_without_a_traceable_link_is_refused(tmp_path):
    def cut(d):
        d["connections"] = [c for c in d["connections"] if c["to"] != "rmap0.S_Pkt"]

    refused(tmp_path, SPW, cut, "the RMAP target rmap0 is not reached over a link")


def test_a_link_that_does_not_start_without_an_external_register_file_is_refused(tmp_path):
    def hide_mib(d):
        d["resolved"]["ports"] = [p for p in d["resolved"]["ports"] if p.get("interface") != "spw0.S_AxiLite"]
        d["resolved"]["addressMap"] = [s for s in d["resolved"]["addressMap"] if s["space"] != "spw0.S_AxiLite"]

    refused(tmp_path, SPW, hide_mib, r"the link spw0\.Spw does not start by itself .* not an external port")


def test_a_spacefibre_port_that_does_not_start_is_refused(tmp_path):
    def no_start(d):
        next(g for g in instance(d, "ofb0")["generics"] if g["name"] == "AutoStart_g")["value"] = False

    refused(tmp_path, SPFI, no_start, r"the link pa0\.Gt does not start by itself")


def test_the_generated_texts():
    for example in (SPW, SPFI):
        system = load(example)
        p = bench.plan(system)
        for text in (generate.harness(system, "-- h\n", p), generate.harness_package(system, "-- h\n", p)):
            assert all(len(line) <= 120 for line in text.splitlines())
    system = load(SPW)
    th = generate.harness(system, "-- h\n")
    pkg = generate.harness_package(system, "-- h\n")
    assert "    i_uvvm : entity uvvm_vvc_framework.ti_uvvm_engine;" in th
    assert "    i_far_end_0 : entity osh_tb.osh_tb_spw_far_end" in th
    assert re.search(r"LinkUp\s+=> osh_link_up\(0\)", th)
    assert "    constant C_OSH_FAR_ENDS     : natural := 1;" in pkg
    assert 'axilite_write(axilite, 0, to_unsigned(16#10#, 8), x"00000038",' in pkg
    assert 'osh_await_link_up(up(0), C_OSH_LINK_TIMEOUT, "spw0.Spw");' in pkg
    assert 'axilite_check(axilite, 1, to_unsigned(16#0#, 10), x"4F4D4101",' in pkg
    assert 'osh_rmap_memory_check(cmd(0), res(0), x"FE", x"00", x"0000000FFC", 0, 1, 2,' in pkg
    assert 'await_completion(axilite, 0, 1 ms, "AXI4-Lite VVC 0");' in pkg
    system = load(SPFI)
    th = generate.harness(system, "-- h\n")
    pkg = generate.harness_package(system, "-- h\n")
    assert "    constant C_PA0_REFCLK_HZ     : positive := 156250000;" in pkg
    assert "    pa0_RefClk <= not pa0_RefClk after C_PA0_REFCLK_PERIOD / 2;" in th
    assert re.search(r"signal pa0_RefClk\s+: std_logic := '0';", th)
    assert "axilite_write" not in pkg


def test_the_readme_describes_the_smoke_test():
    gen_spw, seeds_spw = project.files_of(load(SPW), make_lock(SPW))
    gen_spfi, seeds_spfi = project.files_of(load(SPFI), make_lock(SPFI))
    for seeds in (seeds_spw, seeds_spfi):
        assert "`test_smoke` resets the system and then" in seeds["README.md"]
        assert all(len(line) <= 120 for line in seeds["README.md"].splitlines())
    assert "`spw0.Spw` through the register file of its port (OpenWire `PORT_CTRL`" in seeds_spw["README.md"]
    assert "PORT_CTRL" not in seeds_spfi["README.md"]
    assert "the memory of `rmap0.M_Axi`" in seeds_spfi["README.md"]


def test_new_writes_nothing_when_the_testbench_is_refused(tmp_path):
    def cut(d):
        d["connections"] = [c for c in d["connections"] if c["to"] != "rmap0.S_Pkt"]

    source = variant(tmp_path, SPW, cut)
    with pytest.raises(bench.BenchError):
        project.new(source, tmp_path / "proj", lock=make_lock(SPW), schema_dir=SCHEMAS)
    assert not (tmp_path / "proj").exists()


def test_update_from_a_refused_system_keeps_the_project(tmp_path):
    lk = make_lock(SPW)
    dest = tmp_path / "proj"
    project.new(SPW, dest, lock=lk, schema_dir=SCHEMAS)
    before = {p: p.read_bytes() for p in dest.rglob("*") if p.is_file()}

    def cut(d):
        d["connections"] = [c for c in d["connections"] if c["to"] != "rmap0.S_Pkt"]

    source = variant(tmp_path, SPW, cut)
    with pytest.raises(bench.BenchError):
        project.update(dest, source=source, lock=lk, schema_dir=SCHEMAS)
    assert {p: p.read_bytes() for p in dest.rglob("*") if p.is_file()} == before


def test_width_of_a_port_type():
    assert bench.width("std_logic") == 1
    assert bench.width("std_logic_vector(31 downto 0)") == 32
    assert bench.width("std_logic_vector( 11 downto 0 )") == 12


def test_a_far_end_clock_of_the_spacefibre_adapter_must_be_known(tmp_path):
    def no_lane_domain(d):
        for c in d["resolved"]["clocks"]:
            if c.get("source") == "pa0.LaneClk":
                c["source"] = "elsewhere"

    refused(tmp_path, SPFI, no_lane_domain, r"the lane clock of pa0 or its free-running clock is unknown")
