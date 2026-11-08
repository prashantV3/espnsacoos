"""
Badge callbacks for the Unfold sidebar navigation.
"""
from apps.loans.models import PrimaryLoan, EmergencyAdvance


def active_loans_badge(request):
    """
    Shows a numeric badge of active/approved loans in the sidebar.
    """
    count = PrimaryLoan.objects.filter(status__in=['ACTIVE', 'APPROVED']).count()
    return str(count) if count else None


def overdue_advances_badge(request):
    """
    Shows a warning badge of overdue emergency advances in the sidebar.
    """
    count = EmergencyAdvance.objects.filter(status='OVERDUE').count()
    return str(count) if count else None

