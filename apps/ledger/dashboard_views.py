from decimal import Decimal
from datetime import date
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.loans.models import PrimaryLoan, EmergencyAdvance
from apps.ledger.models import Transaction
from apps.ledger.reports import TrialBalanceReport
from apps.loans.serializers import PrimaryLoanSerializer, EmergencyAdvanceSerializer
from apps.ledger.serializers import TransactionSerializer


class MemberDashboardView(APIView):
    """
    GET /api/v1/dashboard/me/
    Mobile & Web personal dashboard endpoint for the logged-in member:
    - Aggregated loan health & next EMI date
    - Remaining primary loan & emergency advance balances
    - Member deposits/savings balance
    - Total interest and penalties paid
    - Personal financial summary / Trial Balance
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 1. Active Primary Loans
        primary_loans = PrimaryLoan.objects.filter(
            borrower=user,
            status__in=[PrimaryLoan.Status.ACTIVE, PrimaryLoan.Status.APPROVED]
        ).order_by('created_at')

        # 2. Emergency Advances
        emergency_advances = EmergencyAdvance.objects.filter(
            borrower=user,
            status__in=[EmergencyAdvance.Status.ACTIVE, EmergencyAdvance.Status.OVERDUE]
        ).order_by('interest_free_until')

        # 3. Next Upcoming Installment across all active loans
        next_emi_date = None
        next_emi_amount = Decimal('0.00')

        for loan in primary_loans:
            due_date = loan.get_next_installment_date()
            if due_date:
                if next_emi_date is None or due_date < next_emi_date:
                    next_emi_date = due_date
                    next_emi_amount = loan.emi_amount or Decimal('0.00')

        # 4. Aggregated Balances
        total_loan_balance = sum(
            (loan.get_remaining_principal() for loan in primary_loans),
            Decimal('0.00')
        )
        total_emergency_balance = sum(
            (adv.get_total_outstanding() for adv in emergency_advances),
            Decimal('0.00')
        )
        total_debt_balance = total_loan_balance + total_emergency_balance

        # 5. Overdue checks for overall health
        has_overdue_advances = any(adv.is_overdue() for adv in emergency_advances)
        loan_health_status = 'ACTION_REQUIRED' if has_overdue_advances else 'GOOD'

        # 6. Member Financial Summary (Deposits, Interest Paid, Net Position)
        financial_summary = TrialBalanceReport.generate_member_financial_summary(user)

        # 7. Recent Transactions (last 5)
        recent_trxs = Transaction.objects.filter(user=user).order_by('-created_at')[:5]

        return Response({
            'member': {
                'id': user.id,
                'member_id': user.member_id,
                'name': f"{user.first_name} {user.last_name}".strip() or user.username,
                'username': user.username,
                'email': user.email,
                'role': user.role,
            },
            'summary': {
                'overall_health': loan_health_status,
                'total_remaining_balance': float(total_debt_balance),
                'primary_loan_balance': float(total_loan_balance),
                'emergency_advance_balance': float(total_emergency_balance),
                'deposit_balance': financial_summary['deposit_balance'],
                'total_interest_paid': financial_summary['total_interest_paid'],
                'total_penalties_paid': financial_summary['total_penalties_paid'],
                'next_installment': {
                    'due_date': next_emi_date.isoformat() if next_emi_date else None,
                    'amount': float(next_emi_amount),
                }
            },
            'active_primary_loans': PrimaryLoanSerializer(primary_loans, many=True).data,
            'emergency_advances': EmergencyAdvanceSerializer(emergency_advances, many=True).data,
            'recent_transactions': TransactionSerializer(recent_trxs, many=True).data,
            'trial_balance_summary': financial_summary,
        })

