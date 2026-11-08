"""
Unfold Admin Dashboard Callback.
Supplies the rich KPI cards and chart data displayed on /admin/.
"""
from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum

from apps.ledger.models import Account, Transaction, LedgerEntry
from apps.loans.models import PrimaryLoan, EmergencyAdvance
from apps.users.models import GlobalSettings


def dashboard_callback(request, context):
    """
    Injected into the Unfold admin dashboard template context.
    Provides KPI cards, chart data, and quick stats for the admin home.
    """
    # Ensure chart of accounts exists
    accounts = Account.get_or_create_standard_accounts()
    cash_balance = accounts['1010'].get_net_balance()
    loans_receivable = accounts['1020'].get_net_balance()
    advances_receivable = accounts['1030'].get_net_balance()
    member_deposits = accounts['2010'].get_net_balance()
    interest_income = accounts['4010'].get_net_balance()
    penalty_income = accounts['4020'].get_net_balance()

    # Loan & advance counts
    active_loans_count = PrimaryLoan.objects.filter(status__in=['ACTIVE', 'APPROVED']).count()
    pending_loans_count = PrimaryLoan.objects.filter(status='PENDING').count()
    overdue_advances_count = EmergencyAdvance.objects.filter(status='OVERDUE').count()
    active_advances_count = EmergencyAdvance.objects.filter(status='ACTIVE').count()

    # Total transaction volume
    tx_total = Transaction.objects.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    tx_count = Transaction.objects.count()

    # Settings
    global_settings = GlobalSettings.get_settings()

    # Trial Balance health check
    total_debits = LedgerEntry.objects.filter(entry_type='DEBIT').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_credits = LedgerEntry.objects.filter(entry_type='CREDIT').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    is_balanced = (total_debits == total_credits)

    # Build KPI cards for the Unfold dashboard template
    context["kpi_stats"] = [
        {
            "title": _("Cash & Bank Liquidity"),
            "metric": f"${cash_balance:,.2f}",
            "description": _("Account 1010 — Total liquid reserves"),
            "icon": "account_balance",
            "color": "success",
        },
        {
            "title": _("Active Loans Outstanding"),
            "metric": f"${loans_receivable:,.2f}",
            "description": f"{active_loans_count} active / {pending_loans_count} pending approval",
            "icon": "credit_card",
            "color": "info",
        },
        {
            "title": _("Member Savings (Liabilities)"),
            "metric": f"${member_deposits:,.2f}",
            "description": _("Account 2010 — Total SACCOS liability to members"),
            "icon": "savings",
            "color": "warning",
        },
        {
            "title": _("Interest Income Earned"),
            "metric": f"${interest_income:,.2f}",
            "description": _("Account 4010 — Recognized revenue from loan interest"),
            "icon": "trending_up",
            "color": "success",
        },
        {
            "title": _("Emergency Advances"),
            "metric": f"${advances_receivable:,.2f}",
            "description": f"{active_advances_count} active, {overdue_advances_count} overdue",
            "icon": "bolt",
            "color": "danger" if overdue_advances_count > 0 else "warning",
        },
        {
            "title": _("Trial Balance Status"),
            "metric": "BALANCED ✓" if is_balanced else "⚠ UNBALANCED",
            "description": f"DR ${total_debits:,.2f} = CR ${total_credits:,.2f}",
            "icon": "balance",
            "color": "success" if is_balanced else "danger",
        },
    ]

    context["global_settings"] = global_settings
    context["total_tx_volume"] = float(tx_total)
    context["total_tx_count"] = tx_count
    context["is_balanced"] = is_balanced

    # Recent transactions summary
    context["recent_transactions"] = Transaction.objects.select_related(
        'user', 'created_by', 'target_loan', 'target_emergency'
    ).order_by('-created_at')[:8]

    return context

