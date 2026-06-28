import uuid
from django.db import models
from django.utils import timezone

class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        """Soft delete all matching records in bulk."""
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Permanently delete records in bulk."""
        return super().delete()

    def alive(self):
        """Filter only active/alive records."""
        return self.filter(is_deleted=False)

    def dead(self):
        """Filter only soft-deleted records."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        """Override to exclude soft-deleted records by default."""
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self):
        """Explicitly query all records, including soft-deleted ones."""
        return SoftDeleteQuerySet(self.model, using=self._db)


class BaseModel(models.Model):
    """
    Base model that provides UUID primary keys, creation and update timestamps,
    and soft-delete functionality.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()  # Access all objects including deleted

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Perform soft delete by marking is_deleted = True."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=['is_deleted', 'deleted_at'])

    def restore(self, using=None):
        """Restore a soft-deleted object."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(using=using, update_fields=['is_deleted', 'deleted_at'])
