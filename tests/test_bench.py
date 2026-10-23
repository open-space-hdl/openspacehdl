"""Tests of the plan of the generated testbench (openspacehdl.bench) and of the generated texts that use it."""

import functools
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
ENC = FIX / "encrypted_spp_over_spw" / "encrypted_spp_over_spw.composer.json"
IMG = FIX / "compressed_images_over_spw" / "compressed_images_over_spw.composer.json"


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
    assert dict(far.generics) == {"LinkClkHz_g": bench.hz(link), "ClkHz_g": bench.hz(user), "RunDiv_g": "2",
                                  "Index_g": "0"}
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
                                  "ModelIdx_g": "1", "Index_g": "0"}
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
    # The packets of spp0 follow it to virtual channel 0
    assert [(s.far, s.vc) for s in p.sends] == [(0, 0)] and [(r.far, r.vc) for r in p.receives] == [(0, 0)]


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
    for example in (SPW, SPFI, ENC, IMG):
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


def set_generic(d: dict, iid: str, name: str, value, vhdl: str) -> None:
    g = next(g for g in instance(d, iid)["generics"] if g["name"] == name)
    g["value"], g["vhdl"] = value, vhdl


def spp_errors() -> list[tuple[int, str, int]]:
    return [(0x0A0, "ERR_TX1", 0), (0x0A4, "ERR_TX2", 0), (0x0A8, "ERR_TX3", 0), (0x0AC, "ERR_TX4", 0),
            (0x0B0, "ERR_RX1", 0), (0x0B4, "ERR_RX2", 0), (0x0B8, "ERR_RX3", 0), (0x0BC, "ERR_RX4", 0),
            (0x0C0, "ERR_RX5", 0), (0x0C4, "ERR_RX6", 0)]


def test_the_stream_plan_of_a_spacefibre_node():
    p = bench.plan(load(SPFI))
    assert p.sends == [bench.StreamSend("spp0.S_Tx[0]", 0, "spp0", 0, 1, 0x100, 28, 32, (7, 301))]
    assert p.receives == [bench.StreamReceive("spp0.M_Rx[0]", 1, "spp0", 0, 1, 0x200, 'x"FE"', 0x5A, 22, 32,
                                              (5, 259))]
    assert p.chains == [] and p.key_loads == [] and p.stream_notes == []
    assert [(c.instance, c.vvc, c.reads) for c in p.counters] == [
        ("spp0", 2, [(0x080, "TX_PACKETS", 2), (0x084, "RX_PACKETS", 2), *spp_errors()])]
    assert p.spp_clocks == ["Clk_sys"]


def test_a_spacewire_node_without_streams():
    p = bench.plan(load(SPW))
    assert (p.sends, p.receives, p.chains, p.key_loads, p.counters, p.spp_clocks) == ([], [], [], [], [], [])


def test_the_stream_plan_of_an_encryption_chain():
    p = bench.plan(load(ENC))
    assert p.chains == [bench.StreamChain("frm0.S_In", 0, "bytes", 32, "spp0", 0, 0, 0x123, "ocr0", 4096,
                                          message_bytes=4096 + 259)]
    # A message that is not a multiple of 16 bytes and spans two chunks
    assert p.chains[0].message_bytes % 16 != 0 and p.chains[0].message_bytes > p.chains[0].chunk_bytes
    assert p.key_loads == [bench.KeyLoad("ocr0", 0, 256)]
    assert [r.endpoint for r in p.receives] == ["spp0.M_Rx[0]"] and p.sends == []
    counters = {c.instance: c.reads for c in p.counters}
    # The chunks are counted at run time: None
    assert counters["spp0"][:2] == [(0x080, "TX_PACKETS", None), (0x084, "RX_PACKETS", 2)]
    assert counters["ocr0"][0] == (0x090, "ENCRYPTIONS", None)
    assert all(v == 0 for _, _, v in counters["ocr0"][1:]) and len(counters["ocr0"]) == 9


def test_the_stream_plan_of_a_compression_chain():
    p = bench.plan(load(IMG))
    assert [(c.endpoint, c.kind, c.data_width, c.samples, c.ocr, c.apid) for c in p.chains] == [
        ("ocp0.In", "samples", 12, 128 * 128 * 16, "ocr0", 0x123)]
    assert p.key_loads == [bench.KeyLoad("ocr0", 0, 256)]


def test_a_chain_without_the_dense_output_stays_idle(tmp_path):
    system = load(variant(tmp_path, ENC, lambda d: set_generic(d, "ocr0", "DenseOutput_g", False, "false")),
                  make_lock(ENC))
    p = bench.plan(system)
    assert p.chains == [] and p.key_loads == []
    assert p.stream_notes == ["`frm0.S_In` stays idle: its ocr_core does not have the dense output"]
    # The receive port is still checked, the counters of spp0 with it
    assert [r.endpoint for r in p.receives] == ["spp0.M_Rx[0]"]
    assert [c.instance for c in p.counters] == ["spp0"]
    readme = project.files_of(system, make_lock(ENC))[1]["README.md"]
    assert ("Streams and counters the tests leave out:\n\n- `frm0.S_In` stays idle: its ocr_core does not have the "
            "dense output.") in readme


def test_an_spp_core_without_its_cptp_layer_stays_idle(tmp_path):
    p = bench.plan(load(variant(tmp_path, SPFI, lambda d: set_generic(d, "spp0", "Encapsulation_g", False, "false")),
                        make_lock(SPFI)))
    assert p.sends == [] and p.receives == [] and p.counters == []
    assert p.stream_notes == [f"`spp0.{port}` stays idle: spp0 its CPTP layer is removed (Encapsulation_g false)"
                              for port in ("S_Tx[0]", "M_Rx[0]")]


def _xtime(a: int) -> int:
    return ((a << 1) ^ (0x1B if a & 0x80 else 0)) & 0xFF


def _mul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a, b = _xtime(a), b >> 1
    return r


@functools.cache
def _sbox() -> list[int]:
    """The S-box of FIPS 197 (5.1.1): the inverse in GF(2^8), then the affine transformation."""
    out = []
    for a in range(256):
        inv = 1
        for _ in range(254):  # a^254 = a^-1 in GF(2^8), 0 for a = 0
            inv = _mul(inv, a)
        rot = 0
        for k in range(1, 5):
            rot ^= ((inv << k) | (inv >> (8 - k))) & 0xFF
        out.append(inv ^ rot ^ 0x63)
    return out


def aes_block(key: bytes, block: bytes) -> bytes:
    """AES encryption of one block (FIPS 197), for the check of the published test keys."""
    sbox = _sbox()
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [sbox[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _xtime(rcon)
        elif nk > 6 and i % nk == 4:
            t = [sbox[b] for b in t]
        w.append([a ^ b for a, b in zip(w[i - nk], t)])
    s = [b ^ k for b, k in zip(block, sum(w[0:4], []))]
    for r in range(1, nr + 1):
        s = [sbox[b] for b in s]
        s = [s[4 * ((i // 4 + i % 4) % 4) + i % 4] for i in range(16)]  # ShiftRows, the state column by column
        if r < nr:
            mixed = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                mixed += [_mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3], a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3],
                          a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3), _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)]
            s = mixed
        s = [b ^ k for b, k in zip(s, sum(w[4 * r:4 * r + 4], []))]
    return bytes(s)


def test_the_test_keys_are_the_published_ones():
    plain = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
    # The function itself: NIST SP 800-38A, F.1.1 (ECB-AES128, block 1)
    assert aes_block(bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c"), plain).hex() == \
        "3ad77bb40d7a3660a89ecaf32466ef97"
    keys = {bits: bytes.fromhex(k) for bits, (k, _) in generate.TEST_KEYS.items()}
    # AES-128: the GCM specification, test case 3: H = E(K, 0^128)
    assert aes_block(keys[128], bytes(16)).hex() == "b83b533708bf535d0aa6e52980d53b78"
    # AES-192 and AES-256: NIST SP 800-38A, F.1.3 and F.1.5 (ECB, block 1)
    assert aes_block(keys[192], plain).hex() == "bd334f1d6e45f25ff712a214571fa5cc"
    assert aes_block(keys[256], plain).hex() == "f3eed1bdb5d2a03c064b5a7e3db181f8"
    # The IV of test case 3: fixed field || invocation counter
    assert f"{generate.TEST_IV_FIXED:08x}{generate.TEST_IV_COUNT:016x}" == "cafebabefacedbaddecaf888"


def test_the_generated_stream_test():
    system = load(SPFI)
    pkg = generate.harness_package(system, "-- h\n")
    th = generate.harness(system, "-- h\n")
    assert re.search(r"Index_g\s+=> 0", th)
    # The smoke test and the stream test bring the system up
    assert pkg.count("        osh_bring_up(rst, axilite, up);") == 2 and "    procedure osh_stream_test(" in pkg
    # Declaration and body of both test procedures
    for name in ("osh_stream_test", "osh_image_test"):
        head = (f"    procedure {name}(\n        signal rst       : out   std_logic;\n        signal axilite   : inout "
                "t_vvc_target_record;\n        signal axistream : inout bitvis_vip_axistream.td_target_support_pkg."
                "t_vvc_target_record;\n        signal up        : in    std_logic_vector)")
        assert pkg.count(head + ";\n") == 1 and pkg.count(head + " is\n") == 1
    assert "        wait for 2100 * C_CLK_SYS_PERIOD;" in pkg
    assert "        shared_axistream_vvc_config(0).bfm_config.max_wait_cycles :=" in pkg
    assert '        osh_link_check(0, 1, osh_cptp_header(x"FE", x"00") & osh_space_packet(16#100#, false, false, 1,' \
        in pkg
    assert '        osh_link_send(0, 1, osh_cptp_header(x"FE", x"5A") & osh_space_packet(16#200#, false, false, 0,' \
        in pkg
    assert "osh_axis_user(2, std_logic_vector(to_unsigned(16#168200#, 22)))," in pkg
    assert 'axilite_check(axilite, 2, to_unsigned(16#80#, 11), x"00000002",' in pkg
    assert "C_OSH_TEST_KEY" not in pkg
    pkg = generate.harness_package(load(ENC), "-- h\n")
    assert "    -- Test key, not for use in a mission: the AES-256 key of NIST SP 800-38A, example F.1.5" in pkg
    assert '        x"603DEB1015CA71BE2B73AEF0857D7781" & x"1F352C073B6108D72D9810A30914DFF4";' in pkg
    assert 'to_unsigned(16#5C#, 8), C_OSH_TEST_KEY_256(31 downto 0), "ocr0: KEY7");' in pkg
    assert 'to_unsigned(16#6C#, 8), x"80000100",' in pkg
    assert "4096, 4355, 3, C_OSH_CHAIN_TIMEOUT, v_chunks(0)," in pkg
    assert "std_logic_vector(to_unsigned(v_chunks(0), 32))" in pkg
    pkg = generate.harness_package(load(IMG), "-- h\n")
    # The image goes to the image test; the stream test keeps the receive port
    body = pkg[pkg.index("package body"):]
    stream = body[body.index("    procedure osh_stream_test("):body.index("    procedure osh_image_test(")]
    image = body[body.index("    procedure osh_image_test("):]
    assert "osh_samples" not in stream and "axistream_expect(axistream, 1," in stream and "KEY_LOAD" not in stream
    assert "        for I in 0 to 31 loop" in image and "osh_samples(I * 8192, 8192, 12, " in image
    assert "KEY_LOAD slot 0" in image and "axistream_expect" not in image
    assert 'to_unsigned(16#84#, 11), x"00000000",' in image and 'to_unsigned(16#84#, 11), x"00000002",' in stream
    pkg = generate.harness_package(load(SPW), "-- h\n")
    # Without a stream the stream test only logs: the smoke test alone brings the system up
    assert "no stream the test serves (README)" in pkg and pkg.count("        osh_bring_up(rst, axilite, up);") == 1


def test_the_readme_describes_the_stream_test():
    for example in (SPW, SPFI, ENC, IMG):
        readme = project.files_of(load(example), make_lock(example))[1]["README.md"]
        section = readme[readme.index("## The stream test"):readme.index("The bench components")]
        assert all(len(line) <= 120 for line in section.splitlines())
    readme = project.files_of(load(SPW), make_lock(SPW))[1]["README.md"]
    assert "The system has no stream that `test_streams` serves" in readme
    readme = project.files_of(load(SPFI), make_lock(SPFI))[1]["README.md"]
    assert "`test_streams` resets the system, brings its links up" in readme
    assert "far end of `pa0.Gt` (virtual channel 1)" in readme
    readme = project.files_of(load(ENC), make_lock(ENC))[1]["README.md"]
    assert "the AES-256 key of NIST SP 800-38A, example F.1.5" in readme and "not for use in a mission" in readme
    assert "one message of 4355 bytes at `frm0.S_In`" in readme and ", 2 chunks;" in readme
    assert "not their ciphertext and tag" in readme and "test_image_stream" not in readme
    seeds = project.files_of(load(IMG), make_lock(IMG))[1]
    assert "`test_image_stream` resets the system" in seeds["README.md"]
    assert "one image of 262144 samples at `ocp0.In`" in seeds["README.md"]
    assert '"*test_smoke" "*test_streams"' in seeds["README.md"]
    tb = seeds["sim/tb/compressed_images_over_spw_tb.vhd"]
    assert '            elsif run("test_image_stream") then' in tb
    assert "                osh_image_test(osh_rst, AXILITE_VVCT, AXISTREAM_VVCT, osh_link_up);" in tb
    tb = project.files_of(load(ENC), make_lock(ENC))[1]["sim/tb/encrypted_spp_over_spw_tb.vhd"]
    assert "test_image_stream" not in tb
