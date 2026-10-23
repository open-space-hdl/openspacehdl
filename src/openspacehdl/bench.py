"""Plan of the generated system testbench (docs/design.md, section 6.3).

For a checked system (openspacehdl.composer.load) the plan names the bench component of osh_tb that serves every
external interface, with its generics and its port map in the harness, the far end of every link, and the steps of
the smoke test: the start of the links whose port does not start by itself, the ID register of every register bank
(through the AXI4-Lite VVC of its port, or with RMAP through the far end of the link that carries its RMAP target),
and the memory check of every RMAP target whose memory interface is external.

The plan refuses, with every reason, a system whose testbench the generator cannot make: an RMAP target that is not
reached over a link of the system the bench can trace (directly on an OpenWire port, or through an OpenSPP N-Char
adapter on a virtual channel of an OpenFibre port), a link port that does not start and whose register file is not an
external port, a far end clock that is not a clock port of the system.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from openspacehdl.composer import Interface, Port, System
from openspacehdl.errors import OshError

OWR = "openwire/owr_core"
OMAP = "openrmap/omap_core"
NCHAR = "openspp/spp_nchar"
OFB = "openfibre/ofb_core"
PA = "openfibre/ofb_pa_gty"

# OpenWire PORT_CTRL (register 0x10): AUTO_START (bit 3), DRIVER_EN (bit 4) and RECEIVER_EN (bit 5)
OWR_PORT_CTRL = 0x10
OWR_START = 0x38
# The memory of an external AXI4 master (osh_tb_axi_mem): size, the seed of its initial data and of the data written
# by the memory check, and the start of the check, 4 bytes before a 4 KB boundary
MEM_SIZE = 16384
MEM_FILL_SEED = 1
MEM_DATA_SEED = 2
MEM_CHECK_ADDR = 0x1000 - 4
MEM_INSTANCES = 8
# Far ends of SpaceFibre: the model of the system's adapters uses control record 0, far end k uses record k + 1
SPFI_MODEL_RECORDS = 7

AXILITE_SIGNALS = ("AwAddr", "AwValid", "AwReady", "WData", "WStrb", "WValid", "WReady", "BResp", "BValid", "BReady",
                   "ArAddr", "ArValid", "ArReady", "RData", "RResp", "RValid", "RReady")
AXI_SIGNALS = ("AwAddr", "AwLen", "AwSize", "AwBurst", "AwValid", "AwReady", "WData", "WStrb", "WLast", "WValid",
               "WReady", "BResp", "BValid", "BReady", "ArAddr", "ArLen", "ArSize", "ArBurst", "ArValid", "ArReady",
               "RData", "RResp", "RLast", "RValid", "RReady")
AXI_REQUIRED = ("AwAddr", "AwValid", "AwReady", "WData", "WValid", "WReady", "BValid", "BReady", "ArAddr", "ArValid",
                "ArReady", "RData", "RValid", "RReady")


class BenchError(OshError):
    """The testbench of the system cannot be generated; reasons lists every reason."""

    def __init__(self, entity: str, reasons: list[str]):
        self.reasons = reasons
        super().__init__(f"the testbench of {entity} cannot be generated:\n" + "\n".join(f"  - {r}" for r in reasons))


@dataclass
class Component:
    """One instance of a bench component in the harness."""

    entity: str
    label: str
    endpoint: str
    generics: list[tuple[str, str]]
    ports: list[tuple[str, str]]


@dataclass
class Clock:
    """A clock the harness generates on an input pin of the system (the reference clock of a SpaceFibre adapter)."""

    port: str
    name: str
    hz: int


@dataclass
class Start:
    """A link start through the register file of the link port: an AXI4-Lite write."""

    endpoint: str
    vvc: int
    addr: int
    addr_width: int
    value: int


@dataclass
class RegisterCheck:
    """The ID register of a register bank (value None: the bank has none; its base is read and must answer OKAY)."""

    bank: str
    via: str  # "axilite" or "rmap"
    index: int  # AXI4-Lite VVC or far end
    addr: int
    addr_width: int
    value: str | None
    tla: str = ""
    key: str = ""


@dataclass
class MemoryCheck:
    """The memory check of an RMAP target whose memory is the osh_tb_axi_mem instance mem."""

    space: str
    far: int
    mem: int
    tla: str
    key: str
    addr: int = MEM_CHECK_ADDR


@dataclass
class Plan:
    components: list[Component] = field(default_factory=list)
    clocks: list[Clock] = field(default_factory=list)
    far_ends: list[str] = field(default_factory=list)  # pin endpoint of far end k
    starts: list[Start] = field(default_factory=list)
    checks: list[RegisterCheck] = field(default_factory=list)
    memory_checks: list[MemoryCheck] = field(default_factory=list)


def width(port_type: str) -> int:
    """Bits of a port type: std_logic, or std_logic_vector(<n> downto 0)."""
    m = re.fullmatch(r"std_logic_vector\s*\(\s*(\d+)\s+downto\s+(\d+)\s*\)", port_type.strip())
    if m:
        return int(m.group(1)) - int(m.group(2)) + 1
    return 1


def ident(text: str) -> str:
    """The name part of a VHDL constant of the harness package for a port: C_<IDENT>_HZ, C_<IDENT>_PERIOD."""
    return "".join(ch if ch.isalnum() else "_" for ch in text).upper()


def hz(port: str) -> str:
    """The constant of the harness package with the frequency of a clock port (or of a clock pin)."""
    return f"C_{ident(port)}_HZ"


def _literal(text: str) -> str:
    """A hexadecimal value of the Composer file ("0x4F4D4101") as a 32-bit VHDL literal."""
    return f'x"{int(text, 16):08X}"'


class _System:
    """Lookups in the resolved netlist and the user's connections of a system."""

    def __init__(self, system: System):
        self.system = system
        r = system.data["resolved"]
        self.instances = {i["id"]: i for i in r.get("instances", [])}
        self.blocks = {b["id"]: b for b in system.data.get("catalogSubset", {}).get("blocks", [])}
        self.domains = {c["id"]: c for c in r.get("clocks", [])}
        self.clock_ports = {p.name: p for p in system.clocks}
        self.peers: dict[str, list[str]] = {}
        for c in system.data.get("connections", []):
            self.peers.setdefault(c["from"], []).append(c["to"])
            self.peers.setdefault(c["to"], []).append(c["from"])
        self.interfaces = {i.endpoint: i for i in system.interfaces}

    def block(self, inst: str) -> str | None:
        return self.instances.get(inst, {}).get("block")

    def generic(self, inst: str, name: str):
        for g in self.instances.get(inst, {}).get("generics", []):
            if g["name"] == name:
                return g
        return None

    def value(self, inst: str, name: str, default=None):
        g = self.generic(inst, name)
        return default if g is None or g.get("value") is None else g["value"]

    def vhdl(self, inst: str, name: str, default: str) -> str:
        g = self.generic(inst, name)
        return default if g is None or not g.get("vhdl") else g["vhdl"]

    def actual(self, inst: str, port: str) -> str | None:
        for p in self.instances.get(inst, {}).get("ports", []):
            if p["name"] == port:
                return p.get("actual")
        return None

    def peer(self, endpoint: str) -> str | None:
        found = self.peers.get(endpoint, [])
        return found[0] if len(found) == 1 else None

    def spec(self, iface: Interface) -> dict:
        b = self.blocks.get(iface.block, {})
        return next((i for i in b.get("interfaces", []) if i.get("name") == iface.name), {})

    def clock_hz(self, port: str) -> int:
        d = self.domains.get(self.clock_ports[port].domain or "", {})
        return int(round(d.get("frequencyHz", 0)))

    def interface_clock(self, iface: Interface) -> str | None:
        """The clock port of the system that clocks an interface."""
        name = self.spec(iface).get("clock")
        actual = self.actual(iface.instance, name) if name else None
        return actual if actual in self.clock_ports else None


def _signals(iface: Interface) -> dict[str, Port]:
    return {p.signal: p for p in iface.ports if p.signal}


def plan(system: System) -> Plan:
    """The plan of the testbench of a checked system; raises BenchError with every reason."""
    s = _System(system)
    out = Plan()
    reasons: list[str] = []
    axilite: dict[str, tuple[int, int]] = {}  # endpoint -> (VVC index, address width)
    memories: dict[str, int] = {}  # endpoint -> osh_tb_axi_mem instance
    fars: dict[str, int] = {}  # pin endpoint -> far end index
    streams = 0
    spfi = 0

    for iface in system.interfaces:
        sig = _signals(iface)
        clk = s.interface_clock(iface)
        where = f"the interface {iface.endpoint}"
        if iface.type == "axi4lite":
            missing = [n for n in AXILITE_SIGNALS if n not in sig]
            if missing or clk is None:
                reasons.append(f"{where} lacks {', '.join(missing) or 'a clock port of the system'}")
                continue
            if width(sig["WData"].type) != 32:
                reasons.append(f"{where} has {width(sig['WData'].type)}-bit data; the AXI4-Lite VVC of the bench "
                               f"has 32")
                continue
            n = len(axilite)
            aw = width(sig["AwAddr"].type)
            axilite[iface.endpoint] = (n, aw)
            out.components.append(Component(
                "osh_tb_axilite_master", f"i_axilite_{n}", iface.endpoint,
                [("Instance_g", str(n)), ("AddrWidth_g", str(aw))],
                [("Clk", clk)] + [(name, sig[name].name) for name in AXILITE_SIGNALS]))
        elif iface.kind == "stream":
            if clk is None or not {"data", "valid", "ready"} <= set(sig):
                lacks = "a clock port of the system" if clk is None else "data, valid or ready"
                reasons.append(f"{where} lacks {lacks}")
                continue
            master = iface.role == "sink"
            gens = [("Instance_g", str(streams)), ("DataWidth_g", str(width(sig["data"].type))),
                    ("KeepWidth_g", str(width(sig["keep"].type) if "keep" in sig else 0)),
                    ("UserWidth_g", str(width(sig["user"].type) if "user" in sig else 0))]
            ports = [("Clk", clk)] + [(formal, sig[key].name) for formal, key in
                                      (("Data", "data"), ("Keep", "keep"), ("User", "user"), ("Last", "last"),
                                       ("Valid", "valid"), ("Ready", "ready")) if key in sig]
            out.components.append(Component("osh_tb_axis_master" if master else "osh_tb_axis_slave",
                                            f"i_axis_{streams}", iface.endpoint, gens, ports))
            streams += 1
        elif iface.type == "axi4" and iface.role == "master":
            missing = [n for n in AXI_REQUIRED if n not in sig]
            aw = width(sig["AwAddr"].type) if "AwAddr" in sig else 0
            if missing or clk is None:
                reasons.append(f"{where} lacks {', '.join(missing) or 'a clock port of the system'}")
                continue
            if not 12 <= aw <= 64 or len(memories) >= MEM_INSTANCES:
                reasons.append(f"{where}: the memory responder serves 12 to 64 address bits and at most "
                               f"{MEM_INSTANCES} memories")
                continue
            m = len(memories)
            memories[iface.endpoint] = m
            dw = width(sig["WData"].type)
            ties = {"AwLen": 'x"00"', "ArLen": 'x"00"', "AwSize": f'"{int(math.log2(dw // 8)):03b}"',
                    "ArSize": f'"{int(math.log2(dw // 8)):03b}"', "AwBurst": '"01"', "ArBurst": '"01"',
                    "WStrb": "(others => '1')", "WLast": "'1'"}
            ports = [("Clk", clk), ("Rst", "osh_rst")]
            for name in AXI_SIGNALS:
                if name in sig:
                    ports.append((f"S_Axi_{name}", sig[name].name))
                elif name in ties:
                    ports.append((f"S_Axi_{name}", ties[name]))
            out.components.append(Component(
                "osh_tb_axi_mem", f"i_axi_mem_{m}", iface.endpoint,
                [("Instance_g", str(m)), ("AddrWidth_g", str(aw)), ("DataWidth_g", str(dw)),
                 ("SizeBytes_g", str(MEM_SIZE)), ("Seed_g", str(MEM_FILL_SEED))], ports))
        elif iface.type in ("spw.ds", "spfi.serial"):
            fars[iface.endpoint] = len(out.far_ends)
            out.far_ends.append(iface.endpoint)
        elif iface.type == "axi4":
            reasons.append(f"{where} is an AXI4 slave; this version of the generated testbench does not serve AXI4 "
                           f"slaves, a later version adds the UVVM AXI4 VVC for them")

    for endpoint, k in fars.items():
        iface = s.interfaces[endpoint]
        sig = _signals(iface)
        inst = iface.instance
        where = f"the link {endpoint}"
        if iface.type == "spw.ds":
            if not {"d_out", "s_out", "d_in", "s_in"} <= set(sig):
                reasons.append(f"{where} lacks a line of d_out, s_out, d_in, s_in")
                continue
            user, link = s.actual(inst, "UserClk"), s.actual(inst, "LinkClk")
            if user not in s.clock_ports or link not in s.clock_ports:
                reasons.append(f"{where}: the clocks of {inst} are not clock ports of the system")
                continue
            if s.clock_hz(user) < 1_000_000:
                reasons.append(f"{where}: the user clock of {inst} is slower than 1 MHz")
                continue
            out.components.append(Component(
                "osh_tb_spw_far_end", f"i_far_end_{k}", endpoint,
                [("LinkClkHz_g", hz(link)), ("ClkHz_g", hz(user)),
                 ("RunDiv_g", str(s.value(inst, "RunDiv_g", 1)))],
                [("Clk", user), ("LinkClk", link), ("Rst", "osh_rst"),
                 ("Spw_DOut", sig["d_in"].name), ("Spw_SOut", sig["s_in"].name),
                 ("Spw_DIn", sig["d_out"].name), ("Spw_SIn", sig["s_out"].name),
                 ("LinkUp", f"osh_link_up({k})"), ("Cmd", f"osh_rmap_cmd({k})"), ("Res", f"osh_rmap_res({k})")]))
            starts = s.value(inst, "LinkStart_g", False) or s.value(inst, "AutoStart_g", False)
            if not starts or s.value(inst, "LinkDisabled_g", False):
                mib = axilite.get(f"{inst}.S_AxiLite")
                if mib is None:
                    reasons.append(f"{where} does not start by itself (LinkStart_g and AutoStart_g of {inst} are "
                                   f"false) and the register file of {inst} is not an external port")
                    continue
                out.starts.append(Start(endpoint, mib[0], OWR_PORT_CTRL, mib[1], OWR_START))
        else:
            if not {"tx_p", "tx_n", "rx_p", "rx_n", "refclk"} <= set(sig):
                reasons.append(f"{where} lacks a pin of tx_p, tx_n, rx_p, rx_n, refclk")
                continue
            port = (s.peer(f"{inst}.Phy") or "").split(".")[0]
            if s.block(port) != OFB:
                reasons.append(f"{where}: the adapter {inst} is not connected to an OpenFibre port")
                continue
            lane = next((d for d in s.domains.values() if d.get("source") == f"{inst}.LaneClk"), None)
            sys_clk = s.actual(inst, "FreeRunClk")
            if lane is None or sys_clk not in s.clock_ports:
                reasons.append(f"{where}: the lane clock of {inst} or its free-running clock is unknown")
                continue
            if not (s.value(port, "LaneStart_g", False) or s.value(port, "AutoStart_g", True)):
                reasons.append(f"{where} does not start by itself (LaneStart_g and AutoStart_g of {port} are false); "
                               f"this version of the generated testbench does not start it through the register file")
                continue
            if spfi >= SPFI_MODEL_RECORDS:
                reasons.append(f"{where}: the model of the adapters has records for {SPFI_MODEL_RECORDS} far ends")
                continue
            refclk = sig["refclk"].name
            out.clocks.append(Clock(refclk, f"reference clock of {inst} (its lane clock)",
                                    int(round(lane["frequencyHz"]))))
            out.components.append(Component(
                "osh_tb_spfi_far_end", f"i_far_end_{k}", endpoint,
                [("NumLanes_g", str(width(sig["tx_p"].type))), ("NumVc_g", str(s.value(port, "NumVc_g", 8))),
                 ("VcInDepth_g", str(s.value(port, "VcInDepth_g", 256))), ("RmapVc_g", "-1"),
                 ("RefClkHz_g", hz(refclk)), ("SysClkHz_g", hz(sys_clk)), ("ModelIdx_g", str(spfi + 1))],
                [("RefClk", sig["refclk"].name), ("ClkSys", sys_clk), ("Rst", "osh_rst"),
                 ("Gt_TxP", sig["rx_p"].name), ("Gt_TxN", sig["rx_n"].name),
                 ("Gt_RxP", sig["tx_p"].name), ("Gt_RxN", sig["tx_n"].name),
                 ("LinkUp", f"osh_link_up({k})"), ("Cmd", f"osh_rmap_cmd({k})"), ("Res", f"osh_rmap_res({k})")]))
            spfi += 1

    for space in system.data["resolved"].get("addressMap") or []:
        name, kind = space["space"], space["kind"]
        banks = space.get("banks", [])
        if kind == "port":
            vvc = axilite.get(name)
            if vvc is None:
                reasons.append(f"the address space {name} is not an external AXI4-Lite port")
                continue
            for b in banks:
                idr = s.blocks.get(b["block"], {}).get("idRegister")
                offset = int(idr["address"], 16) if idr else 0
                out.checks.append(RegisterCheck(f"{b['instance']}.{b['interface']}", "axilite", vvc[0],
                                                b["base"] + offset, vvc[1], _literal(b["id"]) if idr else None))
        elif kind == "master":
            target = name.split(".")[0]
            external = memories.get(name)
            if not banks and external is None:
                continue
            link = _trace(s, target)
            if link is None:
                reasons.append(f"the RMAP target {target} is not reached over a link the generated testbench can "
                               f"trace (directly on an OpenWire port, or through an OpenSPP N-Char adapter on a "
                               f"virtual channel of an OpenFibre port)")
                continue
            pins, vc = link
            k = fars.get(pins)
            if k is None:
                reasons.append(f"the RMAP target {target} is reached over {pins}, which is not an external link")
                continue
            comp = next((c for c in out.components if c.label == f"i_far_end_{k}"), None)
            if comp is None:  # the far end itself is refused; its reason is recorded
                continue
            if vc is not None:
                comp.generics = [(g, str(vc) if g == "RmapVc_g" else v) for g, v in comp.generics]
            tla, key = s.vhdl(target, "La0_g", 'x"FE"'), s.vhdl(target, "Key_g", 'x"00"')
            for b in banks:
                idr = s.blocks.get(b["block"], {}).get("idRegister")
                offset = int(idr["address"], 16) if idr else 0
                out.checks.append(RegisterCheck(f"{b['instance']}.{b['interface']}", "rmap", k, b["base"] + offset,
                                                40, _literal(b["id"]) if idr else None, tla, key))
            if external is not None:
                out.memory_checks.append(MemoryCheck(name, k, external, tla, key))
        else:
            reasons.append(f"the address space {name} has the kind {kind}, which the generated testbench does not know")

    if reasons:
        raise BenchError(system.entity, reasons)
    return out


def _trace(s: _System, target: str) -> tuple[str, int | None] | None:
    """The external pins of the link that carries an RMAP target and its virtual channel (None on SpaceWire)."""
    if s.block(target) != OMAP:
        return None
    src = s.peer(f"{target}.S_Pkt") or ""
    inst, _, port = src.partition(".")
    if s.block(inst) == OWR and port == "M_Pkt":
        return f"{inst}.Spw", None
    if s.block(inst) == NCHAR and port == "M_NChar":
        m = re.fullmatch(r"(\w+)\.M_Vc\[(\d+)\]", s.peer(f"{inst}.S_Link") or "")
        if m and s.block(m.group(1)) == OFB:
            pa = (s.peer(f"{m.group(1)}.Phy") or "").split(".")[0]
            if s.block(pa) == PA:
                return f"{pa}.Gt", int(m.group(2))
    return None
