from unittest.mock import Mock

import pytest

from src.care.care_provider import CareSearch, CareResult
from src.care.care_provider_renderer import CareProviderRenderer
from src.care.google_place_care_provider import GooglePlaceCareProvider


@pytest.fixture
def setup_renderer():
    renderer = CareProviderRenderer()
    care_provider = Mock()
    renderer.care_provider = care_provider
    return renderer


def test_render_success(setup_renderer):
    renderer = setup_renderer

    renderer.care_provider.find.return_value = [CareResult('test', 'test', 'test phone', 'test', '4', 11),
                                                CareResult('test2', 'test2', '', 'test2')]

    result_html = renderer.render(CareSearch(['test']))

    assert "Sure thing. I have found 2 best doctors near you" in result_html
    assert "test" in result_html
    assert "test2" in result_html
    assert "No reviews" in result_html
    assert "4 ⭐, 11 reviews" in result_html
    assert "No phone number" in result_html
    assert "<a class='text-blue underline' href='tel:test phone' target='_blank'>test phone</a>" in result_html


def test_render_empty_result(setup_renderer):
    renderer = setup_renderer

    renderer.care_provider.find.return_value = []

    result_html = renderer.render(CareSearch(['test']))

    assert result_html == ""


def test_render_failure(setup_renderer):
    renderer = setup_renderer

    renderer.care_provider.find.side_effect = GooglePlaceCareProvider.GoogleFindCareException("test", 500)

    with pytest.raises(GooglePlaceCareProvider.GoogleFindCareException):
        renderer.render(CareSearch(['test']))

    assert renderer.care_provider.find.call_count == 1





