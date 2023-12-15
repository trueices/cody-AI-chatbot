import datetime
import logging
import os

import cachetools
import requests


class EhrService:
    service_cache = cachetools.TTLCache(maxsize=1000, ttl=24 * 60 * 60)

    def __init__(self):
        self.api_key = os.getenv('AKUTE_API_KEY')
        self.akute_base_url = os.getenv('AKUTE_BASE_URL')

    def all_supported_state(self) -> set:
        """
        Fetches all supported states by Akute
        :return:
        """
        cached_states = EhrService.service_cache.get('all_supported_state')

        if cached_states:
            return cached_states

        prescribers = self._all_prescribers()

        supported_states = set()
        for prescriber in prescribers:
            licenses_ = prescriber['licenses']

            for license_details in licenses_:
                expiration_date = datetime.datetime.strptime(
                    license_details['expirationDate'], '%Y-%m-%d')
                if expiration_date > datetime.datetime.today():
                    supported_states.add(license_details['state'].lower())

        EhrService.service_cache['all_supported_state'] = supported_states

        return supported_states

    def _all_prescribers(self) -> dict:
        """
        Fetch all prescribers
        :return:
        """
        if EhrService.service_cache.get('all_prescribers'):
            return EhrService.service_cache['all_prescribers']

        url = f'{self.akute_base_url}/v1/users'
        headers = {
            'X-API-KEY': f'{self.api_key}'
        }

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            logging.error(
                f'Failed to fetch all supported states. Response: {response.text}')
            return []

        prescribers = response.json()
        EhrService.service_cache['all_prescribers'] = prescribers

        return prescribers

    def match_prescriber(self, search_params: dict) -> dict:
        """
        Match prescriber. Rite now in version 1.a this is really simple, but this is where most of the validation
        and matching logic will be implemented.
        """
        prescribers = self._all_prescribers()

        prescribers_with_license = []
        for prescriber in prescribers:
            if 'Prescriber' not in prescriber['roles']:
                continue

            licenses_ = prescriber['licenses']
            for license_details in licenses_:
                expiration_date = datetime.datetime.strptime(
                    license_details['expirationDate'], '%Y-%m-%d')
                if expiration_date > datetime.datetime.today() and license_details['state'].lower() == search_params[
                    'state'].lower():
                    prescribers_with_license.append(prescriber)
                    break

        for prescriber in prescribers_with_license:
            if prescriber.get('bio'):
                return prescriber

        if len(prescribers_with_license) > 0:
            prescriber = prescribers_with_license[0]

            prescriber['bio'] = f"""{prescriber['first_name']} {prescriber['last_name']},

Medical School: NA
Specialty: NA
Experience: NA
Pronouns: NA
"""
            return prescriber

        return {}

    def create_patient(self, patient_data: dict) -> dict:
        """
        Create a patient
        """
        url = f'{self.akute_base_url}/v1/patients'
        headers = {
            'X-API-KEY': f'{self.api_key}'
        }

        patient_data['status'] = 'active'

        response = requests.post(url, headers=headers, data=patient_data)

        if response.status_code != 201:
            logging.error(
                f'Failed to create patient. Response: {response.text}')

        return response.json()

    def create_task(self, task_data: dict) -> dict:
        """
        Create a task
        """
        url = f'{self.akute_base_url}/v1/tasks'
        headers = {
            'X-API-KEY': f'{self.api_key}'
        }

        response = requests.post(url, headers=headers, json=task_data)

        if response.status_code != 201:
            logging.error(f'Failed to create task. Response: {response.text}')

        return response.json()

    def get_plan(self, patient_id: str, start_date) -> str:
        """
        Gets the latest plan by patient id and start date
        The patient id is used to identify the patient.
        In case of multiple notes, the assumption is that the latest note will have the certified plan for the current task.
        This may ofc change in the future with more complex logic.
        """
        url = f'{self.akute_base_url}/v1/notes?patient_id={patient_id}&limit=10&service_date_start={start_date}&status=final'
        headers = {
            'X-API-KEY': f'{self.api_key}'
        }

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            logging.error(f'Failed to fetch notes. Response: {response.text}')

        responses: dict = response.json()

        # Return the latest response sorted by service date
        latest_note = sorted(
            responses, key=lambda x: x['service_date'], reverse=True)[0]
        # Capture plan by matching title
        return next((section['text'] for section in latest_note['sections'] if section['title'] == 'Plan'), None)
