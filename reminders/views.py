from rest_framework import viewsets, permissions
from drf_spectacular.utils import extend_schema
from reminders.models import Reminder
from reminders.serializers import ReminderSerializer
from rewards.models import Reward
from rest_framework.exceptions import PermissionDenied


class ReminderViewSet(viewsets.ModelViewSet):
    """
    Create, list, update and delete expiry reminders for user rewards.
    Celery Beat runs `check_and_send_due_reminders_task` every 10 minutes.
    """
    serializer_class = ReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return only reminders belonging to the authenticated user's rewards."""
        qs = Reminder.objects.filter(
            reward__user=self.request.user
        ).select_related('reward', 'reward__category')

        # Optional filter: ?is_sent=true/false
        is_sent = self.request.query_params.get('is_sent')
        if is_sent is not None:
            qs = qs.filter(is_sent=is_sent.lower() == 'true')

        # Optional filter: ?reward_id=<uuid>
        reward_id = self.request.query_params.get('reward_id')
        if reward_id:
            qs = qs.filter(reward__id=reward_id)

        return qs

    def perform_create(self, serializer):
        """Validate that the reward being reminded belongs to the request user."""
        reward = serializer.validated_data.get('reward')
        if reward.user != self.request.user:
            raise PermissionDenied("You cannot create a reminder for another user's reward.")
        serializer.save()

    @extend_schema(summary="List reminders")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Create a reminder")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(summary="Retrieve a reminder")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(summary="Update a reminder")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(summary="Partially update a reminder")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(summary="Delete a reminder")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
