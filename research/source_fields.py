"""JSON metadata field whose private source references are resolved on access."""

from django.db import models
from django.db.models.query_utils import DeferredAttribute

from research.source_storage import load_sources


class SourceDescriptor(DeferredAttribute):
    def __set__(self, instance, value):
        instance.__dict__[self.field.attname] = value

    def __get__(self, instance, cls=None):
        value = super().__get__(instance, cls)
        if instance is None or instance.__dict__.get("_saving_source_references", False):
            return value
        hydrated = load_sources(instance, value)
        instance.__dict__[self.field.attname] = hydrated
        return hydrated


class SourceJSONField(models.JSONField):
    descriptor_class = SourceDescriptor
