from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import MethodNotAllowed

from apps.ledger.models import Account, Transaction, LedgerEntry
from apps.ledger.serializers import AccountSerializer, TransactionSerializer, TransactionCreateSerializer
from apps.ledger.reports import TrialBalanceReport
from apps.users.permissions import IsAdminOrSuperUser, IsOwnerOrAdmin


class TransactionViewSet(viewsets.ModelViewSet):
    """
    Transactions Endpoint:
    - POST: Admin/Financial Operator records deposits, repayments, disbursements.
    - GET: Admins view all organization transactions; Members view only their own.
    - Immutability: Modifications and deletions are strictly blocked.
    """
    queryset = Transaction.objects.all().select_related(
        'user', 'target_loan', 'target_emergency', 'created_by'
    ).prefetch_related('ledger_entries__account')

    def get_permissions(self):
        if self.action == 'create':
            return [IsAdminOrSuperUser()]
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return TransactionCreateSerializer
        return TransactionSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Transaction.objects.none()

        qs = self.queryset
        # Role-based query filtering
        if not (user.role in ['ADMIN', 'SUPERUSER'] or user.is_staff or user.is_superuser):
            qs = qs.filter(user=user)

        # Optional query filters
        user_id = self.request.query_params.get('user_id')
        loan_id = self.request.query_params.get('loan_id')
        emergency_id = self.request.query_params.get('emergency_id')
        trx_type = self.request.query_params.get('type')

        if user_id and (user.role in ['ADMIN', 'SUPERUSER'] or user.is_staff):
            qs = qs.filter(user_id=user_id)
        if loan_id:
            qs = qs.filter(target_loan_id=loan_id)
        if emergency_id:
            qs = qs.filter(target_emergency_id=emergency_id)
        if trx_type:
            qs = qs.filter(transaction_type=trx_type)

        return qs

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed('PUT', detail='Historical transactions are strictly immutable and cannot be modified.')

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed('PATCH', detail='Historical transactions are strictly immutable and cannot be modified.')

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed('DELETE', detail='Historical transactions are strictly immutable and cannot be deleted.')


class TrialBalanceReportView(APIView):
    """
    GET /api/v1/reports/trial-balance/
    Organization-wide financial report verifying double-entry Debits == Credits.
    Accessible to Admins and Superusers.
    """
    permission_classes = [IsAdminOrSuperUser]

    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        data = TrialBalanceReport.generate_organization_trial_balance(
            start_date=start_date,
            end_date=end_date
        )
        return Response(data, status=status.HTTP_200_OK)


class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Chart of accounts viewset for financial reporting.
    """
    queryset = Account.objects.all().order_by('code')
    serializer_class = AccountSerializer
    permission_classes = [IsAdminOrSuperUser]


class BalanceSheetReportView(APIView):
    """
    GET /api/v1/reports/balance-sheet/
    Organization Balance Sheet: Assets = Liabilities + Equity
    """
    permission_classes = [IsAdminOrSuperUser]

    def get(self, request):
        data = TrialBalanceReport.generate_balance_sheet()
        return Response(data, status=status.HTTP_200_OK)


class IncomeStatementReportView(APIView):
    """
    GET /api/v1/reports/income-statement/
    Organization Profit & Loss / Income Statement: Revenue - Expenses = Net Surplus
    """
    permission_classes = [IsAdminOrSuperUser]

    def get(self, request):
        data = TrialBalanceReport.generate_income_statement()
        return Response(data, status=status.HTTP_200_OK)


class PortfolioAgingReportView(APIView):
    """
    GET /api/v1/reports/aging/
    Loan & advance portfolio health aging analysis and PAR (Portfolio at Risk).
    """
    permission_classes = [IsAdminOrSuperUser]

    def get(self, request):
        data = TrialBalanceReport.generate_portfolio_aging_report()
        return Response(data, status=status.HTTP_200_OK)
