"""Unit tests de SlotAssigner (src/domain/services/account_slot_assigner.py) --
generalizacion de _assign_slot_for_hash/sidecars de flow_animation_service.py."""

import threading

import pytest

from src.domain.services.account_slot_assigner import SlotAssigner

HASH_A = "gt:hashA"
HASH_B = "gt:hashB"
HASH_LEGACY = "hashSinPrefijo"


@pytest.fixture
def assigner(tmp_path):
    return SlotAssigner(sidecar_dir=tmp_path, prefix="gt_account", num_slots=4, valid_hash_prefix="gt:")


def test_hash_nuevo_toma_el_primer_slot_libre(assigner):
    idx = assigner.assign_slot(HASH_A)
    assert idx == 0


def test_mismo_hash_siempre_devuelve_el_mismo_slot(assigner):
    idx1 = assigner.assign_slot(HASH_A)
    idx2 = assigner.assign_slot(HASH_A)
    assert idx1 == idx2 == 0


def test_dos_hashes_distintos_nunca_comparten_slot(assigner):
    idx_a = assigner.assign_slot(HASH_A)
    idx_b = assigner.assign_slot(HASH_B)
    assert idx_a != idx_b


def test_slot_taken_on_disk_nunca_se_pisa(assigner):
    # Slot 0 y 1 ya ocupados por otro medio (p. ej. cookie pegada a mano) --
    # el hash nuevo debe caer en el primer slot realmente libre (2).
    idx = assigner.assign_slot(HASH_A, slot_taken_on_disk=lambda i: i in (0, 1))
    assert idx == 2


def test_sin_slots_libres_devuelve_none(assigner):
    for i in range(4):
        assigner.assign_slot(f"gt:hash{i}")
    assert assigner.assign_slot("gt:hashExtra") is None


def test_sidecar_valido_en_disco_se_reusa_entre_instancias(tmp_path):
    a1 = SlotAssigner(sidecar_dir=tmp_path, prefix="gt_account", num_slots=4, valid_hash_prefix="gt:")
    idx = a1.assign_slot(HASH_A)
    a1.write_sidecar(idx, HASH_A, {"email": "a@example.com"})

    # Instancia nueva (simula reinicio del backend, _hash_to_idx en memoria vacio)
    # -- debe reconstruir el mismo slot leyendo el sidecar en disco.
    a2 = SlotAssigner(sidecar_dir=tmp_path, prefix="gt_account", num_slots=4, valid_hash_prefix="gt:")
    idx2 = a2.assign_slot(HASH_A)
    assert idx2 == idx


def test_sidecar_con_prefijo_invalido_se_autolimpia_y_libera_el_slot(tmp_path):
    a1 = SlotAssigner(sidecar_dir=tmp_path, prefix="gt_account", num_slots=4, valid_hash_prefix="gt:")
    a1.write_sidecar(0, HASH_LEGACY, {})
    sidecar_path = a1._sidecar_path(0)
    assert sidecar_path.is_file()

    a2 = SlotAssigner(sidecar_dir=tmp_path, prefix="gt_account", num_slots=4, valid_hash_prefix="gt:")
    idx = a2.assign_slot(HASH_A)
    assert idx == 0
    # El sidecar huerfano se borro al leerlo (read_sidecar lo detecto invalido).
    assert not sidecar_path.is_file()


def test_write_sidecar_persiste_meta_extra(tmp_path):
    a = SlotAssigner(sidecar_dir=tmp_path, prefix="gt_account", num_slots=4, valid_hash_prefix="gt:")
    a.write_sidecar(0, HASH_A, {"email": "user@example.com"})
    data = a.read_sidecar(0)
    assert data == {"account_hash": HASH_A, "email": "user@example.com", "ts": pytest.approx(data["ts"])}


def test_dos_hashes_nuevos_simultaneos_nunca_comparten_indice(assigner):
    """Condicion de carrera: dos hashes nunca antes vistos registrandose casi al
    mismo tiempo (dos content scripts reconectando al reiniciar la app) no deben
    leer el mismo estado 'libre' en disco y terminar compartiendo slot."""
    results: dict[str, int | None] = {}

    def _register(h: str):
        results[h] = assigner.assign_slot(h)

    threads = [threading.Thread(target=_register, args=(f"gt:concurrent{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assigned = [v for v in results.values() if v is not None]
    assert len(assigned) == len(set(assigned)), "dos hashes distintos terminaron con el mismo slot"
    assert len(assigned) == 4
