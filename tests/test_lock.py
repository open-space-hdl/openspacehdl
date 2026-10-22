"""Tests of the lock manifest rules and of the manifest model (openspacehdl.lock), on plain data."""

import copy

import pytest

from openspacehdl import lock
from openspacehdl.errors import LockError, OshError

C_OWR = "1" * 40
C_OCP = "2" * 40
C_OLO = "3" * 40
C_RS = "4" * 40
C_UVVM = "5" * 40
C_FIX = "6" * 40
C_WEB = "7" * 40


def inputs() -> lock.Inputs:
    """A consistent set: two cores, Open Logic FT and reference-systems."""
    return lock.Inputs(
        website_commit=C_WEB,
        catalog_id="abcdef012345",
        generator="0.9.8-beta",
        catalog_sources=[
            {"id": "openwire", "name": "OpenWire", "repo": "openwire", "commit": C_OWR, "library": "openwire",
             "fileList": "compile_order.txt", "fileListFormat": "files", "verifiedWith": "4.7.0-ft.6"},
            {"id": "opencompact", "name": "OpenCompact", "repo": "opencompact", "commit": C_OCP,
             "library": "opencompact", "fileList": "compile_order.txt", "fileListFormat": "files",
             "verifiedWith": "4.7.0-ft.6"},
            {"id": "olo", "name": "Open Logic FT", "repo": "open-logic-ft", "tag": "4.7.0-ft.8", "commit": C_OLO,
             "library": "olo", "fileList": "compile_order.txt", "fileListFormat": "files"},
        ],
        cards={"openwire": {"public": True, "trl": 3}, "opencompact": {"public": True, "trl": 3},
               "open1553": {"public": False}},
        refsys_tag="v0.1.1",
        refsys_commit=C_RS,
        refsys_submodules={"opencompact": C_OCP, "open-logic-ft": C_OLO},
        refsys_composer_ref=C_WEB,
        tags={
            "openwire": {"v0.1.0": C_OWR},
            "opencompact": {"v0.1.0": "8" * 40, "v0.1.1": C_OCP},
            "open-logic-ft": {"4.7.0-ft.6": "9" * 40, "4.7.0-ft.8": C_OLO},
            "reference-systems": {"v0.1.1": C_RS},
        },
        published_tags={
            "openwire": {"v0.1.0"},
            "opencompact": {"v0.1.0", "v0.1.1"},
            "open-logic-ft": {"4.7.0-ft.6", "4.7.0-ft.8"},
            "reference-systems": {"v0.1.1"},
        },
        olo_submodules={"3rdParty/en_cl_fix": C_FIX},
        uvvm={"openwire": C_UVVM, "opencompact": C_UVVM},
        models={"openwire": {}},
        licenses={"openwire": "PSI HDL Library License, Version 1.0", "opencompact": "PSI HDL Library License, "
                  "Version 1.0", "open-logic-ft": "PSI HDL Library License, Version 1.0",
                  "reference-systems": "PSI HDL Library License, Version 1.0"},
    )


def src(i: lock.Inputs, sid: str) -> dict:
    return next(s for s in i.catalog_sources if s["id"] == sid)


def test_consistent_set_has_no_violation():
    assert lock.check(inputs()) == []


def _not_a_release(i):
    src(i, "openwire")["commit"] = "a" * 40


def _prerelease_tag_only(i):
    i.tags["openwire"] = {"v0.2.0-rc1": C_OWR}


def _tag_not_published(i):
    i.published_tags["openwire"] = set()


def _refsys_not_a_release(i):
    i.refsys_tag = "develop"


def _refsys_tag_other_commit(i):
    i.tags["reference-systems"]["v0.1.1"] = "b" * 40


def _refsys_tag_not_published(i):
    i.published_tags["reference-systems"] = set()


def _refsys_other_core(i):
    i.refsys_submodules["opencompact"] = "8" * 40


def _no_olo(i):
    i.catalog_sources = [s for s in i.catalog_sources if s["id"] != "olo"]


def _olo_without_tag(i):
    del src(i, "olo")["tag"]


def _olo_tag_missing(i):
    src(i, "olo")["tag"] = "4.7.0-ft.99"


def _olo_tag_not_published(i):
    i.published_tags["open-logic-ft"] = {"4.7.0-ft.6"}


def _olo_commit_not_tag(i):
    src(i, "olo")["commit"] = "c" * 40


def _refsys_other_olo(i):
    i.refsys_submodules["open-logic-ft"] = "9" * 40


def _refsys_without_olo(i):
    del i.refsys_submodules["open-logic-ft"]


def _no_composer_ref(i):
    i.refsys_composer_ref = None


def _other_composer_ref(i):
    i.refsys_composer_ref = "d" * 40


def _card_not_public(i):
    i.cards["openwire"]["public"] = False


def _no_card(i):
    del i.cards["opencompact"]


def _two_uvvm(i):
    i.uvvm["opencompact"] = "e" * 40


def _no_uvvm(i):
    i.uvvm = {}


@pytest.mark.parametrize(
    "mutate, rule, text",
    [
        (_not_a_release, "L1", "openwire"),
        (_prerelease_tag_only, "L1", "openwire"),
        (_tag_not_published, "L1", "not on the remote"),
        (_refsys_not_a_release, "L1", "develop"),
        (_refsys_tag_other_commit, "L1", "reference-systems"),
        (_refsys_tag_not_published, "L1", "reference-systems"),
        (_refsys_other_core, "L2", "opencompact: the catalog pins 2222222 (v0.1.1), reference-systems v0.1.1 pins "
                                   "8888888 (v0.1.0)"),
        (_no_olo, "L3", "no Open Logic FT"),
        (_olo_without_tag, "L3", "without a tag"),
        (_olo_tag_missing, "L3", "4.7.0-ft.99"),
        (_olo_tag_not_published, "L3", "not on the remote"),
        (_olo_commit_not_tag, "L3", "ccccccc"),
        (_refsys_other_olo, "L3", "9999999"),
        (_refsys_without_olo, "L3", "pins none"),
        (_no_composer_ref, "L4", "no tools/composer_ref.txt"),
        (_other_composer_ref, "L4", "ddddddd"),
        (_card_not_public, "L5", "openwire"),
        (_no_card, "L5", "opencompact"),
        (_two_uvvm, "L10", "eeeeeee"),
        (_no_uvvm, "L10", "none"),
    ],
)
def test_each_rule(mutate, rule, text):
    i = inputs()
    mutate(i)
    violations = lock.check(i)
    assert [v.rule for v in violations] == [rule], violations
    assert text in violations[0].message


def test_a_core_reference_systems_does_not_use_is_not_compared():
    i = inputs()
    assert "openwire" not in i.refsys_submodules
    src(i, "openwire")["commit"] = C_OWR
    assert lock.check(i) == []


def test_build_writes_the_manifest():
    m = lock.build(inputs(), "0.1.0")
    assert m["format"] == "openspacehdl-lock" and m["version"] == 1 and m["package"] == "0.1.0"
    assert m["website"] == {"repository": "open-space-hdl/open-space-hdl.github.io", "commit": C_WEB,
                            "catalog": "abcdef012345", "generator": "0.9.8-beta"}
    assert m["referenceSystems"]["tag"] == "v0.1.1" and m["referenceSystems"]["commit"] == C_RS
    olo = m["openLogic"]
    assert (olo["tag"], olo["commit"], olo["library"]) == ("4.7.0-ft.8", C_OLO, "olo")
    assert olo["submodules"] == {"3rdParty/en_cl_fix": C_FIX}
    assert m["uvvm"] == {"repository": "UVVM/UVVM", "commit": C_UVVM}
    assert [c["id"] for c in m["cores"]] == ["openwire", "opencompact"]
    ocp = m["cores"][1]
    assert (ocp["tag"], ocp["commit"], ocp["verifiedWith"], ocp["trl"]) == ("v0.1.1", C_OCP, "4.7.0-ft.6", 3)
    assert ocp["license"] == "PSI HDL Library License, Version 1.0"


def test_build_takes_the_highest_release_tag_of_a_commit():
    i = inputs()
    i.tags["openwire"] = {"v0.1.0": C_OWR, "v0.10.0": C_OWR, "v0.9.0": C_OWR}
    i.published_tags["openwire"] = {"v0.1.0", "v0.9.0", "v0.10.0"}
    assert lock.build(i, "0.1.0")["cores"][0]["tag"] == "v0.10.0"


def test_build_refuses_with_every_violation():
    i = inputs()
    _refsys_other_core(i)
    _other_composer_ref(i)
    with pytest.raises(LockError) as e:
        lock.build(i, "0.1.0")
    assert "L2" in str(e.value) and "L4" in str(e.value)
    assert isinstance(e.value, OshError)


def test_model_reads_what_build_writes():
    m = lock.build(inputs(), "0.1.0")
    lk = lock.Lock.from_dict(copy.deepcopy(m))
    assert (lk.package, lk.website_commit, lk.refsys_tag, lk.olo_tag, lk.uvvm_commit) == (
        "0.1.0", C_WEB, "v0.1.1", "4.7.0-ft.8", C_UVVM)
    assert [c.id for c in lk.cores] == ["openwire", "opencompact"]
    assert lk.cores[1].verified_with == "4.7.0-ft.6"
    assert lock.dumps(m).endswith("}\n")


@pytest.mark.parametrize("key, value", [("format", "other"), ("version", 2)])
def test_model_refuses_another_format(key, value):
    m = lock.build(inputs(), "0.1.0")
    m[key] = value
    with pytest.raises(LockError):
        lock.Lock.from_dict(m)


def test_load_without_manifest_says_so():
    with pytest.raises(LockError) as e:
        lock.load()
    assert "carries no lock manifest" in str(e.value)
