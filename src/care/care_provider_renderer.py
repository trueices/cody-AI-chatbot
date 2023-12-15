from textwrap import dedent

from src.care.care_provider import CareSearch
from src.care.google_place_care_provider import GooglePlaceCareProvider


# This is the interface between the care provider and the agent to reach find care
class CareProviderRenderer:

    CARE_DISPLAY_TEMPLATE = dedent(
        """\
        <div class='tx-plan'>
        <span>{index}. <a class="text-blue underline" href="{website}" target="_blank">{name}</a></span>
        <ul style="list-style-type:none;">
        <li>{address}</li>
        <li>{phone}</li>
        <li>{rating}</li>
        </ul>
        </div>
        """)

    def __init__(self):
        self.care_provider = GooglePlaceCareProvider()

    def render(self, search_obj: CareSearch) -> str:

        results = self.care_provider.find(search_obj)

        if results.__len__() == 0:
            return ""

        html_response = f"""Sure thing. I have found {results.__len__()} best doctors near you."""

        for i, care in enumerate(results):
            rating = care.rating
            phone = care.phone

            if rating is None:
                rating = "No reviews"
            else:
                rating = f"{rating} ⭐, {care.rating_count} reviews"

            if phone is None or phone == "":
                phone = "No phone number"
            else:
                phone = f"<a class='text-blue underline' href='tel:{phone}' target='_blank'>{phone}</a>"

            html_response += CareProviderRenderer.CARE_DISPLAY_TEMPLATE.format(website=care.website, name=care.name, address=care.address,
                                                          phone=phone, rating=rating, index=i+1)
        return html_response

