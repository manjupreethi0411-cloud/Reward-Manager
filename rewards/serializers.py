from rest_framework import serializers
from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from rewards.models import Category, Reward, RewardAuditLog

class CategorySerializer(serializers.ModelSerializer):
    name_display = serializers.CharField(source='get_name_display', read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'name_display', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class RewardSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all())
    category_info = CategorySerializer(source='category', read_only=True)
    
    # Custom fields mapping to model properties
    code = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    pin = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Reward
        fields = [
            'id', 'category', 'category_info', 'title', 'description', 
            'reward_type', 'status', 'value', 'code', 'pin', 'url', 
            'loyalty_program_name', 'issuer_name', 'issue_date', 'expiry_date', 
            'is_starred', 'is_expired', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        # Additional custom cross-field validations
        issue_date = attrs.get('issue_date')
        expiry_date = attrs.get('expiry_date')
        if expiry_date and issue_date:
            if expiry_date.date() < issue_date:
                raise serializers.ValidationError(
                    {"expiry_date": _("Expiry date cannot be before the issue date.")}
                )
        return attrs


class RewardAuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = RewardAuditLog
        fields = [
            'id', 'reward', 'user', 'user_email', 'action', 'action_display', 
            'change_log', 'ip_address', 'user_agent', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp']


class RewardAnalyticsSerializer(serializers.Serializer):
    total_rewards = serializers.IntegerField(read_only=True)
    active_rewards = serializers.IntegerField(read_only=True)
    used_rewards = serializers.IntegerField(read_only=True)
    expired_rewards = serializers.IntegerField(read_only=True)
    monthly_savings = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )
    rewards_by_category = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )

