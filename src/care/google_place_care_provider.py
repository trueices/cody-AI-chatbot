import os

import requests

from src.care.care_provider import CareProvider, CareSearch, CareResult


class GooglePlaceCareProvider(CareProvider):

    def find(self, search_obj: CareSearch) -> list[CareResult]:
        query = ' '.join(search_obj.search_terms)

        payload = {
            "textQuery": query,
            "rankPreference": "RELEVANCE"
        }

        #  api call to search google places new text search API
        url = 'https://places.googleapis.com/v1/places:searchText'

        headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                   'X-Goog-Api-Key': os.getenv('GOOGLE_API_KEY'),
                   'X-Goog-FieldMask': 'places.displayName,places.websiteUri,places.rating,places.shortFormattedAddress,places.businessStatus,places.internationalPhoneNumber,places.userRatingCount'}

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            raise GooglePlaceCareProvider.GoogleFindCareException(f"Unable to find care: {search_obj.search_terms}",
                                                                  response.status_code)

        data = response.json()
        care_results: list[CareResult] = []
        for place in data.get('places', []):
            if place['businessStatus'] != 'OPERATIONAL':
                continue

            if care_results.__len__() == 3:
                break
            else:
                result = CareResult(place.get('displayName', {}).get('text', None),
                                    place.get('shortFormattedAddress', None),
                                    place.get(
                                        'internationalPhoneNumber', None),
                                    place.get('websiteUri', None),
                                    place.get('rating', None),
                                    place.get('userRatingCount', None))

                care_results.append(result)

        return care_results

    class GoogleFindCareException(Exception):
        def __init__(self, message, code):
            self.message = message
            self.code = code
            super().__init__(self.message)

