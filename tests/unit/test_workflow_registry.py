from __future__ import annotations

from pathlib import Path

from lucid.recorder.registry import WorkflowRegistry
from lucid.recorder.workflow import Workflow, WorkflowStep, WorkflowVariable, slugify


def _make_workflow(**kw) -> Workflow:
    wf = Workflow(name=kw.pop("name", "Yeni fatura oluştur"), **kw)
    wf.append(WorkflowStep(index=0, action="click", intent="click submit"))
    return wf


def test_slugify_ascii_lowercase() -> None:
    assert slugify("Yeni Fatura Oluştur") == "yeni_fatura_olustur"
    assert slugify("Acme Group Raporu!!!") == "acme_group_raporu"
    assert slugify("") == ""


def test_workflow_ensure_slug_populates_from_name() -> None:
    wf = _make_workflow(name="Gmail'de fatura maili hazırla")
    slug = wf.ensure_slug()
    assert slug and slug == wf.slug
    assert "gmail" in slug


def test_registry_add_writes_entry_by_slug(tmp_path: Path) -> None:
    wf = _make_workflow(
        name="Yeni fatura oluştur",
        aliases=["fatura kes", "faturala"],
        target_app="parasut.exe",
        variables=[
            WorkflowVariable(
                name="musteri", description="Müşteri adı", example="Acme Corp", required=True
            )
        ],
    )
    wf.slug = "fatura_kes"
    path = wf.save(tmp_path)

    registry = WorkflowRegistry(tmp_path)
    entry = registry.add(wf, path)
    assert entry.slug == "fatura_kes"
    assert "fatura kes" in entry.aliases
    assert entry.target_app == "parasut.exe"
    listed = registry.list_all()
    assert len(listed) == 1 and listed[0].slug == "fatura_kes"


def test_registry_find_by_slug_alias_and_phrase(tmp_path: Path) -> None:
    wf = _make_workflow(name="Yeni fatura oluştur", aliases=["fatura kes", "faturala"])
    wf.slug = "fatura_kes"
    registry = WorkflowRegistry(tmp_path)
    registry.add(wf, wf.save(tmp_path))

    assert registry.find("fatura_kes") is not None
    assert registry.find("fatura kes") is not None
    assert registry.find("faturala") is not None
    # Whole-word containment: "Ahmet'e fatura kes" still matches.
    assert registry.find("Ahmet'e fatura kes lütfen") is not None
    assert registry.find("tamamen alakasız bir cümle") is None


def test_registry_add_is_idempotent(tmp_path: Path) -> None:
    wf = _make_workflow()
    wf.slug = "dup_test"
    path = wf.save(tmp_path)
    registry = WorkflowRegistry(tmp_path)
    registry.add(wf, path)
    registry.add(wf, path)
    assert len(registry.list_all()) == 1


def test_registry_remove(tmp_path: Path) -> None:
    wf = _make_workflow()
    wf.slug = "remove_me"
    registry = WorkflowRegistry(tmp_path)
    registry.add(wf, wf.save(tmp_path))
    assert registry.remove("remove_me") is True
    assert registry.list_all() == []
    assert registry.remove("remove_me") is False
