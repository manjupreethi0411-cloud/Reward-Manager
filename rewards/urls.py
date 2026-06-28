from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rewards.views import CategoryViewSet, RewardViewSet

app_name = 'rewards'

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'', RewardViewSet, basename='reward')

urlpatterns = [
    path('', include(router.urls)),
]
