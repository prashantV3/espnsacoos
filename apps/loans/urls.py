from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.loans.views import PrimaryLoanViewSet, EmergencyAdvanceViewSet

router = DefaultRouter()
router.register(r'loans', PrimaryLoanViewSet, basename='primary_loan')
router.register(r'emergency-advances', EmergencyAdvanceViewSet, basename='emergency_advance')

urlpatterns = [
    path('', include(router.urls)),
]

