from decimal import Decimal
from datetime import date
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.loans.models import PrimaryLoan, EmergencyAdvance
from apps.loans.serializers import (
    PrimaryLoanSerializer,
    PrimaryLoanCreateSerializer,
    PrimaryLoanApplySerializer,
    EmergencyAdvanceSerializer,
    EmergencyAdvanceCreateSerializer,
    EmergencyAdvanceApplySerializer
)
from apps.users.permissions import IsAdminOrSuperUser, IsOwnerOrAdmin
from apps.ledger.models import Transaction


class PrimaryLoanViewSet(viewsets.ModelViewSet):
    """
    Primary Loan Management:
    - Admins/Superusers can view all loans and create/approve/disburse loans.
    - Members can apply for loans and view their own loans/amortization schedules.
    """
    queryset = PrimaryLoan.objects.all().select_related('borrower', 'approved_by')

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'approve', 'reject', 'disburse']:
            return [IsAdminOrSuperUser()]
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return PrimaryLoanCreateSerializer
        elif self.action == 'apply':
            return PrimaryLoanApplySerializer
        return PrimaryLoanSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return PrimaryLoan.objects.none()

        if user.role in ['ADMIN', 'SUPERUSER'] or user.is_staff or user.is_superuser:
            return PrimaryLoan.objects.all().select_related('borrower', 'approved_by')
        return PrimaryLoan.objects.filter(borrower=user).select_related('borrower', 'approved_by')

    @action(detail=False, methods=['post'], url_path='apply', permission_classes=[permissions.IsAuthenticated])
    def apply(self, request):
        """
        Allows an authenticated member to submit a loan application.
        """
        serializer = PrimaryLoanApplySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        loan = serializer.save()
        return Response(PrimaryLoanSerializer(loan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """
        Admin approves a pending loan application.
        """
        loan = self.get_object()
        if loan.status != PrimaryLoan.Status.PENDING:
            return Response(
                {'detail': f"Loan cannot be approved from current status '{loan.status}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        loan.status = PrimaryLoan.Status.APPROVED
        loan.approved_by = request.user
        loan.save(update_fields=['status', 'approved_by', 'updated_at'])
        return Response(PrimaryLoanSerializer(loan).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """
        Admin rejects a loan application.
        """
        loan = self.get_object()
        if loan.status != PrimaryLoan.Status.PENDING:
            return Response(
                {'detail': f"Loan cannot be rejected from current status '{loan.status}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        reason = request.data.get('reason', 'Application rejected by administration.')
        loan.status = PrimaryLoan.Status.CLOSED
        loan.purpose = f"{loan.purpose or ''}\n[REJECTED]: {reason}".strip()
        loan.save(update_fields=['status', 'purpose', 'updated_at'])
        return Response(PrimaryLoanSerializer(loan).data)

    @action(detail=True, methods=['post'], url_path='disburse')
    def disburse(self, request, pk=None):
        """
        Admin disburses funds for an approved loan.
        Automatically records the LOAN_DISBURSEMENT Transaction and balanced Ledger entries!
        """
        loan = self.get_object()
        if loan.status not in [PrimaryLoan.Status.APPROVED, PrimaryLoan.Status.PENDING]:
            return Response(
                {'detail': f"Loan cannot be disbursed from current status '{loan.status}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment_method = request.data.get('payment_method', Transaction.PaymentMethod.BANK_TRANSFER)
        reference_number = request.data.get('reference_number', f"DISB-LOAN-{loan.id}")
        notes = request.data.get('notes', f"Disbursement of Primary Loan #{loan.id}")

        trx = Transaction(
            user=loan.borrower,
            transaction_type=Transaction.TransactionType.LOAN_DISBURSEMENT,
            target_loan=loan,
            amount=loan.principal_amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            created_by=request.user
        )
        trx.save()

        loan.refresh_from_db()
        return Response({
            'detail': 'Loan successfully disbursed.',
            'loan': PrimaryLoanSerializer(loan).data,
            'transaction_id': str(trx.transaction_id)
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='amortization-schedule')
    def amortization_schedule(self, request, pk=None):
        """
        Returns full month-by-month repayment schedule for this loan.
        """
        loan = self.get_object()
        schedule = loan.generate_amortization_schedule()
        return Response({
            'loan_id': loan.id,
            'principal_amount': float(loan.principal_amount),
            'interest_rate': float(loan.interest_rate),
            'tenure_months': loan.tenure_months,
            'emi_amount': float(loan.emi_amount) if loan.emi_amount else None,
            'schedule': schedule
        })


class EmergencyAdvanceViewSet(viewsets.ModelViewSet):
    """
    Emergency Advance Management:
    - Admins/Superusers can grant advances and define grace periods.
    - Members can apply and view their advances, remaining grace days, and penalties.
    """
    queryset = EmergencyAdvance.objects.all().select_related('borrower', 'approved_by')

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'disburse']:
            return [IsAdminOrSuperUser()]
        return [permissions.IsAuthenticated(), IsOwnerOrAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return EmergencyAdvanceCreateSerializer
        elif self.action == 'apply':
            return EmergencyAdvanceApplySerializer
        return EmergencyAdvanceSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return EmergencyAdvance.objects.none()

        if user.role in ['ADMIN', 'SUPERUSER'] or user.is_staff or user.is_superuser:
            return EmergencyAdvance.objects.all().select_related('borrower', 'approved_by')
        return EmergencyAdvance.objects.filter(borrower=user).select_related('borrower', 'approved_by')

    @action(detail=False, methods=['post'], url_path='apply', permission_classes=[permissions.IsAuthenticated])
    def apply(self, request):
        """
        Allows an authenticated member to apply for an interest-free emergency advance.
        """
        serializer = EmergencyAdvanceApplySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        advance = serializer.save()
        return Response(EmergencyAdvanceSerializer(advance).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='disburse')
    def disburse(self, request, pk=None):
        """
        Admin disburses funds for an emergency advance.
        Automatically records the EMERGENCY_DISBURSEMENT Transaction and balanced Ledger entries!
        """
        advance = self.get_object()
        if advance.status == EmergencyAdvance.Status.REPAID:
            return Response(
                {'detail': "Advance is already repaid."},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment_method = request.data.get('payment_method', Transaction.PaymentMethod.CASH)
        reference_number = request.data.get('reference_number', f"DISB-EMG-{advance.id}")
        notes = request.data.get('notes', f"Disbursement of Emergency Advance #{advance.id}")

        trx = Transaction(
            user=advance.borrower,
            transaction_type=Transaction.TransactionType.EMERGENCY_DISBURSEMENT,
            target_emergency=advance,
            amount=advance.principal_amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            created_by=request.user
        )
        trx.save()

        advance.refresh_from_db()
        return Response({
            'detail': 'Emergency advance successfully disbursed.',
            'advance': EmergencyAdvanceSerializer(advance).data,
            'transaction_id': str(trx.transaction_id)
        }, status=status.HTTP_200_OK)
