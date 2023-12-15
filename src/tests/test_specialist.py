from src.specialist import Specialist


def test_from_specialist_with_unknown_name():
    specialty = Specialist.from_name('old_name')

    assert specialty == Specialist.Generalist


def test_from_specialist_with_known_name():
    specialty = Specialist.from_name('neurologist')

    assert specialty == Specialist.Neurologist


def test_from_display_name_unknown_default_generalist():
    specialty = Specialist.from_inventory_name('unknown')

    assert specialty == Specialist.Generalist
