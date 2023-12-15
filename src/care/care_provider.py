from abc import abstractmethod, ABC


class CareSearch:
    def __init__(self, search_terms: list[str]):
        self.search_terms = search_terms


class CareResult:
    def __init__(self, name: str, address: str, phone: str, website: str, rating: str = None, rating_count: str = None):
        self.name = name
        self.address = address
        self.phone = phone
        self.website = website
        self.rating = rating
        self.rating_count = rating_count


class CareProvider(ABC):

    @abstractmethod
    def find(self, search_obj: CareSearch) -> list[CareResult]:
        pass
