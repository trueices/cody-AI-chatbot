# TODO - Implement a real ad provider
import os

from src.utils import demo_mode


class Provider:

    def __init__(self, mode: str):
        self.mode = mode

    def diagnosis(self, diag_list: list) -> str:
        demo_match = demo_mode(self.mode)
        if demo_match:
            dx = demo_match.group(1)

            for diag in diag_list:
                if dx in diag.lower():
                    # check if file exists
                    if os.path.exists(f"{os.path.dirname(__file__)}/../demo/{self.mode}/diagnosis.txt"):
                        with (open(f"{os.path.dirname(__file__)}/../demo/{self.mode}/diagnosis.txt", 'r', encoding='utf-8')
                              as file):
                            return file.read()

            return f"Demo not configured properly. Please setup demo properly for mode ${self.mode}."
        else:
            return ""

    def treatment(self, diag: str) -> str:
        demo_match = demo_mode(self.mode)

        if demo_match and demo_match.group(1) in diag.lower():
            if os.path.exists(f"{os.path.dirname(__file__)}/../demo/{self.mode}/treatment.txt"):
                with (open(f"{os.path.dirname(__file__)}/../demo/{self.mode}/treatment.txt", 'r', encoding='utf-8')
                      as file):
                    return file.read()

            return f"Demo not configured properly. Please setup demo properly for mode ${self.mode}."
        else:
            return ""

    def find_care(self):
        demo_match = demo_mode(self.mode)

        if demo_match:
            if os.path.exists(f"{os.path.dirname(__file__)}/../demo/{self.mode}/care.txt"):
                with (open(f"{os.path.dirname(__file__)}/../demo/{self.mode}/care.txt", 'r', encoding='utf-8')
                      as file):
                    return file.read()
            else:
                return f"Demo not configured properly. Please setup demo properly for mode ${self.mode}."
        else:
            return ""
