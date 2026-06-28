from django.urls import path, include
from rest_framework.routers import DefaultRouter
from reminders.views import ReminderViewSet

app_name = 'reminders'

router = DefaultRouter()
router.register(r'', ReminderViewSet, basename='reminder')

urlpatterns = [
    path('', include(router.urls)),
]
