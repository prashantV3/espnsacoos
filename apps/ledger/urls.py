from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.ledger.views import TransactionViewSet, TrialBalanceReportView, AccountViewSet
from apps.ledger.dashboard_views import MemberDashboardView

router = DefaultRouter()
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'accounts', AccountViewSet, basename='account')

urlpatterns = [
    # Dashboard Endpoint
    path('dashboard/me/', MemberDashboardView.as_view(), name='member_dashboard'),

    # Reports
    path('reports/trial-balance/', TrialBalanceReportView.as_view(), name='trial_balance_report'),

    # Transactions & Accounts Routers
    path('', include(router.urls)),
]

