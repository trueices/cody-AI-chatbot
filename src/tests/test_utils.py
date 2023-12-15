from src.specialist import Specialist
from src.sub_specialist import SubSpecialtyDxGroup
from src.utils import map_url_name
from src.agents.utils import load_greetings, GREETINGS_df
from src.agents.utils import load_priority_fields, get_supported_sps, PRIORITY_FIELD_df


def test_loading_of_priority_fields():
    supported_list = get_supported_sps()
    assert len(supported_list) > 0, "No supported specialists/Dx groups supported"

    all_unique_sps = set(PRIORITY_FIELD_df['SPECIALITY/DXGROUP'].str.lower())
    all_supported_sps = set([sp.inventory_name.lower() for sp in supported_list])
    assert all_unique_sps == all_supported_sps, "Some specialists/Dx groups are not supported"

    generalist_fields, _, _ = load_priority_fields(Specialist.Generalist, SubSpecialtyDxGroup.Generalist)

    for sp in supported_list:
        if isinstance(sp, Specialist):
            fields, min_points, confidence_interval = load_priority_fields(sp, SubSpecialtyDxGroup.Generalist)
            if sp != Specialist.Generalist:
                assert fields != generalist_fields, f"Fields for {sp.name} should not be same as Generalist"
            for field, column_dict in fields.items():
                # if column_dict contains key 'COMPULSORY', it's value should be 'No' or 'Yes'.
                if 'COMPULSORY' in column_dict:
                    assert column_dict['COMPULSORY'] in ['No', 'Yes'], \
                        f"Field {field} for specialist {sp.name} contains invalid compulsory value"
        elif isinstance(sp, SubSpecialtyDxGroup):
            fields, min_points, confidence_interval = load_priority_fields(Specialist.Generalist, sp)
            assert fields != generalist_fields, f"Fields for subspecialist {sp.name} should not be same as Generalist"
            # Subs should only contain FILL SCORE
            for field, column_dict in fields.items():
                assert 'FILL SCORE' in column_dict, f"Field {field} for sub {sp.name} does not contain fill score"
                assert len(column_dict) == 1, f"Field {field} for sub {sp.name} contains more than fill score"
        else:
            assert False, f"Specialist/DxGroup {sp} not supported"
        for field, value in fields.items():
            assert isinstance(field, str), f"Field {field} for specialist {sp.name} is not a string"
            score = value['FILL SCORE']
            assert isinstance(score, int), f"Score {score} for field {field} in {sp.name} is not an int"
            assert score > 0, f"Score {score} for field {field} in {sp.name} is not positive"
        assert min_points > 10, f"Min points {min_points} for {sp.name} is not greater than 10"
        assert confidence_interval > 10, f"Confidence interval {confidence_interval} for {sp.name} is not greater than 10"
        assert confidence_interval <= 100, f"Confidence interval {confidence_interval} for {sp.name} is not less than 100"
        assert len(fields) > 0, f"Very few fields for {sp.name}"
        assert len(fields) <= 20, f"Too many fields for {sp.name}"

def test_pf_loading_not_supported():
    fields = load_priority_fields(Specialist.AdverseReactionSpecialist, SubSpecialtyDxGroup.Generalist)
    assert len(fields) > 0, "Fields should be captured for AdverseReactionSpecialist"
    generalist_fields = load_priority_fields(Specialist.Generalist, SubSpecialtyDxGroup.Generalist)
    assert fields == generalist_fields, "AdverseReactionSpecialist should have same fields as Generalist"

def test_loading_of_priority_fields_with_specialist():
    fields_neuro = load_priority_fields(Specialist.Neurologist, SubSpecialtyDxGroup.Generalist)
    fields_migraine = load_priority_fields(Specialist.Neurologist, SubSpecialtyDxGroup.Migraine)
    fields_migraine_2 = load_priority_fields(Specialist.Generalist, SubSpecialtyDxGroup.Migraine)
    assert fields_neuro != fields_migraine, "Neurologist and Migraine should have different fields"
    assert fields_migraine == fields_migraine_2, "Migraine should be recognised irrespective of specialist"
    assert len(fields_neuro) > 0
    assert len(fields_migraine) > 0


def test_greetings_load():
    greetings = load_greetings()

    # Greetings should be unique
    assert len(greetings) == len(set(greetings)), "Greetings are not unique"
    # Greeting values should be unique
    assert len(greetings.values()) == len(greetings), "Greeting values are not unique"

    assert greetings[SubSpecialtyDxGroup.ParkinsonsDisease].get('greeting').startswith(
        "Hello!\n\n\nI'm Cody, your AI Doctor, specializing in Neurology.")
    assert SubSpecialtyDxGroup.Generalist in greetings, "Generalist not found in greetings"
    for spdx in greetings:
        assert greetings[spdx].get('greeting').startswith(
            "Hello!"), f"Does not start with 'Hello!' in {spdx}"
        assert greetings[spdx].get('greeting').count(
            "Hello!") == 1, f"Multiple 'Hello!'s found in {spdx}"


def test_url_recognition():
    # URLs should be unique
    assert len(GREETINGS_df['URLs'].unique()) == len(GREETINGS_df), "URLs are not unique"

    for i, rows in GREETINGS_df.iterrows():
        assert rows.URLs.startswith('cody.md')
        if rows.URLs == 'cody.md':
            # generalist
            assert rows['SPECIALITY/DXGROUP'] == 'general'
            continue
        else:
            rows.URLs = rows.URLs.replace('cody.md/sp/', '')
        sp, dx = map_url_name(rows.URLs)
        # both shouldnt be generalist
        assert sp != Specialist.Generalist or \
               dx != SubSpecialtyDxGroup.Generalist, f"Recognised generalist in {rows.URLs}"
        # atleast one should be recognised
        assert sp.inventory_name.lower() == rows['SPECIALITY/DXGROUP'].lower() or \
               dx.inventory_name.lower() == rows['SPECIALITY/DXGROUP'].lower(), \
            f"Specialist/DxGroup not recognised in {rows.URLs}"


def test_map_url_name_for_speciality():
    specialist, sub_specialist = map_url_name('neurology')

    assert specialist == Specialist.Neurologist
    assert sub_specialist == SubSpecialtyDxGroup.Generalist


def test_map_url_name_for_sub_speciality():
    specialist, sub_specialist = map_url_name('anxiety')

    assert specialist == Specialist.Psychiatrist
    assert sub_specialist == SubSpecialtyDxGroup.Anxiety


def test_map_url_name_for_not_supported_url():
    specialist, sub_specialist = map_url_name('hiv')

    assert specialist == Specialist.Generalist
    assert sub_specialist == SubSpecialtyDxGroup.Generalist
