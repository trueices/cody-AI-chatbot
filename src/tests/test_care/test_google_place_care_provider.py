import pytest
import requests_mock

from src.care.care_provider import CareSearch
from src.care.google_place_care_provider import GooglePlaceCareProvider


def test_find_care_success_filter_out_non_operation(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'test')

    with requests_mock.Mocker() as req:
        post = req.post('https://places.googleapis.com/v1/places:searchText', json={"places": [
            {"displayName": {"text": "test"}, "shortFormattedAddress": "test", "internationalPhoneNumber": "test",
             "websiteUri": "test", "rating": "5", "businessStatus": "OPERATIONAL"},
            {"displayName": {"text": "test2"}, "shortFormattedAddress": "test2", "internationalPhoneNumber": "test2",
             "websiteUri": "test2", "rating": "4", "businessStatus": "CLOSED_PERMANENTLY"},
            {"displayName": {"text": "test3"}, "shortFormattedAddress": "test3", "internationalPhoneNumber": "test3",
             "rating": "3", "businessStatus": "OPERATIONAL"}
        ]})

        provider = GooglePlaceCareProvider()
        results = provider.find(CareSearch(['test']))

        assert results.__len__() == 2
        assert results[0].name == 'test'
        assert results[0].address == 'test'
        assert results[0].phone == 'test'
        assert results[0].website == 'test'
        assert results[0].rating == '5'
        assert post.call_count == 1


def test_find_care_google_failure(monkeypatch):
    monkeypatch.setenv('GOOGLE_API_KEY', 'test')

    with requests_mock.Mocker() as req:
        post = req.post('https://places.googleapis.com/v1/places:searchText', status_code=500)

        with pytest.raises(GooglePlaceCareProvider.GoogleFindCareException) as e:
            provider = GooglePlaceCareProvider()
            provider.find(CareSearch(['test']))

        assert e.value.code == 500
        assert e.value.message == "Unable to find care: ['test']"

        assert post.call_count == 1
