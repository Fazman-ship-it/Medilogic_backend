class ShortIDMixin:
    @property
    def short_id(self):
        return str(self.id).split("-")[0]