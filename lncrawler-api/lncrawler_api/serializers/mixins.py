class ProfileFieldsMixin:
    """One serializer per model, several payload shapes.

    Subclasses declare every field they can emit and set ``field_profiles`` to
    the ordered subset each profile sends. ``profile`` is a constructor kwarg;
    ``default_profile`` is used when it is omitted. ``Meta.fields`` is derived
    from the union of the profiles, so there is a single source of truth.

    ``get_fields`` drops the fields a profile does not emit *before* DRF
    computes ``_readable_fields``, so an excluded ``SerializerMethodField``'s
    method never runs. That is what keeps, say, a card profile from paying for
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

    def get_field_names(self, declared_fields, info):
        # Meta.fields is the ordered union of every profile (first mention wins),
        # so profiles only have to list their own fields once.
        if self.field_profiles:
            union = {}
            for names in self.field_profiles.values():
                for name in names:
                    union.setdefault(name, None)
            return list(union)
        return super().get_field_names(declared_fields, info)

    def get_fields(self):
        fields = super().get_fields()
        profile = self.field_profiles[self.profile]
        missing = [name for name in profile if name not in fields]
        if missing:
            raise AssertionError(
                f"{type(self).__name__}: profile {self.profile!r} references fields "
                f"absent from the serializer: {missing}"
            )
        return {name: fields[name] for name in profile}
