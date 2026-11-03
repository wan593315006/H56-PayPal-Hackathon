"""Preparation errors are observations, not governance or execution decisions."""


class PreparationError(ValueError):
    def __init__(self, code, detail=''):
        self.code = code
        self.detail = detail
        super().__init__(code + (':' + detail if detail else ''))
