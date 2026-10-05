class ProfileFieldsMixin:
    """One serializer per model, several payload shapes.

    Subclasses set ``Meta.fields`` to the union of every profile (DRF builds
    fields from it) and ``field_profiles`` to the ordered subset each profile
    emits. ``profile`` is a constructor kwarg.

    ``get_fields`` drops the fields a profile does not emit *before* DRF
    computes ``_readable_fields``, so an excluded ``SerializerMethodField``'s
    method never runs. That is what keeps, say, a list profile from paying for
    the detail-only ``sources``/``similar_novels``/``reading_lists`` queries.
    """

    default_profile = None
    field_profiles = {}

    def __init__(self, *args, profile=None, **kwargs):
        self.profile = profile or self.default_profile
        if self.profile not in self.field_profiles:
            raise ValueError(
                f"{type(self).__name__}: unknown profile {self.profile!r}; "
                f"expected one of {sorted(self.field_profiles)}"
            )
        super().__init__(*args, **kwargs)

    def get_fields(self):
        fields = super().get_fields()
        profile = self.field_profiles[self.profile]
        missing = [name for name in profile if name not in fields]
        if missing:
            raise AssertionError(
                f"{type(self).__name__}: profile {self.profile!r} references fields "
                f"absent from Meta.fields: {missing}"
            )
        return {name: fields[name] for name in profile}
