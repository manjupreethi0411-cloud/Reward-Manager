import django_filters
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from decimal import Decimal
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from rewards.models import Category, Reward, RewardAuditLog
from rewards.serializers import (
    CategorySerializer,
    RewardSerializer,
    RewardAuditLogSerializer,
    RewardAnalyticsSerializer,
)

class RewardFilter(django_filters.FilterSet):
    expiry_after = django_filters.DateTimeFilter(field_name='expiry_date', lookup_expr='gte')
    expiry_before = django_filters.DateTimeFilter(field_name='expiry_date', lookup_expr='lte')
    min_value = django_filters.NumberFilter(field_name='value', lookup_expr='gte')
    max_value = django_filters.NumberFilter(field_name='value', lookup_expr='lte')

    class Meta:
        model = Reward
        fields = ['category', 'status', 'reward_type', 'issuer_name', 'is_starred']


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Retrieve default categories configured in the database.
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']

    @extend_schema(summary="List categories")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Retrieve category details")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class RewardViewSet(viewsets.ModelViewSet):
    """
    Manage Cashback, Coupons, Gift Cards, Loyalty Points, and Payment App Rewards.
    """
    serializer_class = RewardSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = RewardFilter
    search_fields = ['title', 'description', 'issuer_name', 'loyalty_program_name']
    ordering_fields = ['expiry_date', 'value', 'created_at', 'is_starred']
    ordering = ['-created_at']  # Default sorting

    def get_queryset(self):
        # Enforce owner-only isolation
        return Reward.objects.filter(user=self.request.user).select_related('category')

    @extend_schema(
        summary="List user rewards",
        description="Lists all active, used, or expired rewards. Supports search, filtering, and sorting parameters."
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary="Retrieve reward details")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Create a reward",
        responses={201: RewardSerializer}
    )
    def perform_create(self, serializer):
        reward = serializer.save(user=self.request.user)
        # Log the create action
        RewardAuditLog.log_action(
            reward=reward,
            user=self.request.user,
            action=RewardAuditLog.AuditAction.CREATE,
            change_log={"status": {"new": reward.status}},
            request=self.request
        )

    @extend_schema(summary="Update reward details")
    def perform_update(self, serializer):
        instance = self.get_object()
        
        # Capture original values to record changes
        old_values = {}
        for field in serializer.validated_data:
            if hasattr(instance, field):
                old_values[field] = getattr(instance, field)

        reward = serializer.save()

        # Build differential log
        change_log = {}
        for field, new_value in serializer.validated_data.items():
            old_value = old_values.get(field)
            
            # Serialize object values (like foreign keys)
            if hasattr(old_value, 'id'):
                old_value = str(old_value.id)
            if hasattr(new_value, 'id'):
                new_value = str(new_value.id)
            if isinstance(old_value, Decimal):
                old_value = str(old_value)
            if isinstance(new_value, Decimal):
                new_value = str(new_value)
                
            if old_value != new_value:
                change_log[field] = {"old": old_value, "new": new_value}

        if change_log:
            RewardAuditLog.log_action(
                reward=reward,
                user=self.request.user,
                action=RewardAuditLog.AuditAction.UPDATE,
                change_log=change_log,
                request=self.request
            )

    @extend_schema(summary="Delete a reward")
    def perform_destroy(self, instance):
        # Log deletion action before object gets soft-deleted
        RewardAuditLog.log_action(
            reward=instance,
            user=self.request.user,
            action=RewardAuditLog.AuditAction.DELETE,
            change_log={"status": {"old": instance.status, "new": "DELETED"}},
            request=self.request
        )
        instance.delete()

    @extend_schema(
        summary="Mark reward as used",
        description="Changes the status of a reward to USED.",
        responses={
            200: RewardSerializer,
            400: OpenApiResponse(description="Reward has already been marked as used")
        }
    )
    @action(detail=True, methods=['post'], url_path='mark-used')
    def mark_used(self, request, pk=None):
        reward = self.get_object()
        if reward.status == Reward.RewardStatus.USED:
            return Response(
                {"detail": "Reward has already been marked as used."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = reward.status
        reward.status = Reward.RewardStatus.USED
        reward.save(update_fields=['status'])

        # Log use action
        RewardAuditLog.log_action(
            reward=reward,
            user=request.user,
            action=RewardAuditLog.AuditAction.USE,
            change_log={"status": {"old": old_status, "new": reward.status}},
            request=request
        )

        serializer = self.get_serializer(reward)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Retrieve reward audit history",
        responses={200: RewardAuditLogSerializer(many=True)}
    )
    @action(detail=True, methods=['get'], url_path='audit-logs')
    def audit_logs(self, request, pk=None):
        reward = self.get_object()
        logs = RewardAuditLog.objects.filter(reward=reward).select_related('user')
        serializer = RewardAuditLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Get reward analytics",
        description="Returns total rewards count, counts by status (active, used, expired), monthly savings (based on used rewards), and rewards grouped by category.",
        responses={200: RewardAnalyticsSerializer}
    )
    @action(detail=False, methods=['get'], url_path='analytics')
    def analytics(self, request):
        user_rewards = self.get_queryset()  # isolates to request.user
        
        total_rewards = user_rewards.count()
        active_rewards = user_rewards.filter(status=Reward.RewardStatus.ACTIVE).count()
        used_rewards = user_rewards.filter(status=Reward.RewardStatus.USED).count()
        expired_rewards = user_rewards.filter(status=Reward.RewardStatus.EXPIRED).count()

        # Monthly savings (sum of value of USED rewards, grouped by month of creation)
        from django.db.models import Sum, Count
        from django.db.models.functions import TruncMonth

        monthly_savings_query = (
            user_rewards.filter(status=Reward.RewardStatus.USED, value__isnull=False)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(savings=Sum('value'))
            .order_by('-month')
        )
        
        monthly_savings = []
        for entry in monthly_savings_query:
            if entry['month']:
                month_str = entry['month'].strftime('%Y-%m')
                monthly_savings.append({
                    'month': month_str,
                    'savings': float(entry['savings']) if entry['savings'] else 0.0
                })

        # Rewards by category
        category_query = (
            user_rewards.values('category__id', 'category__name')
            .annotate(count=Count('id'), total_value=Sum('value'))
            .order_by('-count')
        )
        
        cat_choices = dict(Category.CategoryName.choices)
        rewards_by_category = []
        for entry in category_query:
            cat_name = entry['category__name']
            display_name = cat_choices.get(cat_name, cat_name)
            rewards_by_category.append({
                'category_id': str(entry['category__id']) if entry['category__id'] else None,
                'category_name': display_name,
                'count': entry['count'],
                'total_value': float(entry['total_value']) if entry['total_value'] else 0.0
            })

        data = {
            'total_rewards': total_rewards,
            'active_rewards': active_rewards,
            'used_rewards': used_rewards,
            'expired_rewards': expired_rewards,
            'monthly_savings': monthly_savings,
            'rewards_by_category': rewards_by_category
        }
        
        serializer = RewardAnalyticsSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)

