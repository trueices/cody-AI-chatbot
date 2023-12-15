import logging
from enum import Enum


class Specialist(Enum):
    Dentist = ('dentist', 'dental')
    CardiovascularSpecialist = ('cardiovascular_specialist', 'cardiovascular')
    Pulmonologist = ('pulmonologist', 'pulmonology')
    Endocrinologist = ('endocrinologist', 'endocrinology')
    Gastroenterologist = ('gastroenterologist', 'gastroenterology')
    InfectiousDiseaseSpecialist = ('infectious_disease_specialist', 'infectious_disease')
    Neurologist = ('neurologist', 'neurology', "neurology")
    Dermatologist = ('dermatologist', 'dermatology')
    Psychiatrist = ('psychiatrist', 'psychiatry', 'psychiatry')
    Orthopedist = ('orthopedist', 'orthopedics')
    Otolaryngologist = ('otolaryngologist', 'otolaryngology')
    Ophthalmologist = ('opthalmologist', 'opthalmology')
    Urologist = ('urologist', 'urology')
    Gynecologist = ('gynecologist', 'gynecology')
    Pediatrician = ('pediatrician', 'pediatrics')
    SubstanceUseDisorderSpecialist = ('substance_use_disorder_specialist', 'substance_use_disorder')
    RenalSpecialist = ('renal_specialist', 'renal_specialist')
    Allergist = ('allergist', 'allergy')
    Hematologist = ('hematologist', 'hematology')
    Rheumatologist = ('rheumatologist', 'rheumatology')
    AdverseReactionSpecialist = ('adverse_reaction_specialist', 'adverse_reaction')
    Obstetrician = ('obstetrician', 'obstetrics')
    Generalist = ('generalist', 'general')

    def __init__(self, inventory_name: str, display_name_speciality: str, url_keyword: str = ""):
        self.inventory_name = inventory_name
        self.display_name_speciality = display_name_speciality
        self.url_keyword = url_keyword
        if url_keyword == "":
            self.url_keyword = inventory_name

    @staticmethod
    def from_url(url: str):
        for spec in Specialist:
            if spec.url_keyword.lower() == url.lower():
                return spec

        logging.warning(f"Url keyword {url} is not supported. Returning Generalist.")
        return Specialist.Generalist

    @staticmethod
    def from_name(name: str):
        if name is None:
            return Specialist.Generalist
        for spec in Specialist:
            if spec.name.lower() == name.lower():
                return spec

        logging.warning(f"Specialist {name} is not supported. Returning Generalist.")
        return Specialist.Generalist

    @staticmethod
    def from_inventory_name(display_name: str):
        for spec in Specialist:
            if spec.inventory_name.lower() == display_name.lower() or \
                    spec.display_name_speciality.lower() == display_name.lower():
                return spec

        logging.warning(f"Display name {display_name} is not supported for Specialist. Returning Generalist.")
        return Specialist.Generalist
