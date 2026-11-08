from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class PrimaryLoan(models.Model):
    """
    Standard interest-bearing loan with monthly EMI repayment structure.
    Implements 'Fat Models' pattern with mathematical financial calculations.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Approval')
        APPROVED = 'APPROVED', _('Approved')
        ACTIVE = 'ACTIVE', _('Active / Disbursed')
        CLOSED = 'CLOSED', _('Fully Repaid / Closed')
        DEFAULTED = 'DEFAULTED', _('Defaulted')

    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='primary_loans'
    )
    principal_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text=_("Principal loan amount disbursed")
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text=_("Annual interest rate percentage (e.g. 12.00 for 12% p.a.)")
    )
    tenure_months = models.PositiveIntegerField(
        help_text=_("Loan tenure duration in months")
    )
    start_date = models.DateField(
        default=timezone.now,
        help_text=_("Loan start date or first repayment cycle anchor date")
    )
    disbursement_date = models.DateField(
        blank=True,
        null=True,
        help_text=_("Date the loan funds were disbursed to the member")
    )
    emi_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_("Calculated Equated Monthly Installment")
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_primary_loans'
    )
    purpose = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Primary Loan')
        verbose_name_plural = _('Primary Loans')
        ordering = ['-created_at']

    def __str__(self):
        return f"Loan #{self.id} - {self.borrower.username} (${self.principal_amount} @ {self.interest_rate}%)"

    # =========================================================================
    # FINANCIAL LOGIC (Fat Model Methods)
    # =========================================================================

    @staticmethod
    def calculate_emi(principal: Decimal, annual_rate: Decimal, tenure_months: int) -> Decimal:
        """
        Calculates standard reducing-balance Equated Monthly Installment (EMI).
        Formula:
            EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
            where:
                P = Principal
                r = Monthly interest rate = (annual_rate / 100) / 12
                n = tenure in months
        """
        if principal <= 0 or tenure_months <= 0:
            return Decimal('0.00')

        if annual_rate <= 0:
            emi = principal / Decimal(str(tenure_months))
            return emi.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        p = float(principal)
        r = float(annual_rate) / (12 * 100)
        n = int(tenure_months)

        emi_val = p * r * ((1 + r) ** n) / (((1 + r) ** n) - 1)
        return Decimal(str(emi_val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def generate_amortization_schedule(self) -> list:
        """
        Generates full month-by-month loan repayment schedule.
        Returns detailed list with opening balance, interest, principal, EMI, and closing balance.
        """
        schedule = []
        if not self.principal_amount or not self.tenure_months:
            return schedule

        r = (self.interest_rate / Decimal('100')) / Decimal('12')
        emi = self.emi_amount or self.calculate_emi(
            self.principal_amount, self.interest_rate, self.tenure_months
        )

        current_balance = Decimal(str(self.principal_amount))
        anchor_date = self.start_date or (self.disbursement_date or date.today())

        for month in range(1, self.tenure_months + 1):
            due_date = anchor_date + relativedelta(months=month)

            if r > 0:
                interest_payment = (current_balance * r).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                interest_payment = Decimal('0.00')

            # In the final month, reconcile any rounding cents
            if month == self.tenure_months or current_balance < emi:
                principal_payment = current_balance
                month_emi = principal_payment + interest_payment
                closing_balance = Decimal('0.00')
            else:
                principal_payment = emi - interest_payment
                closing_balance = current_balance - principal_payment

            schedule.append({
                'installment_number': month,
                'due_date': due_date.isoformat(),
                'opening_balance': float(current_balance),
                'emi': float(month_emi if (month == self.tenure_months or current_balance < emi) else emi),
                'principal_payment': float(principal_payment),
                'interest_payment': float(interest_payment),
                'closing_balance': float(max(closing_balance, Decimal('0.00')))
            })

            current_balance = closing_balance
            if current_balance <= 0:
                break

        return schedule

    def get_total_principal_paid(self) -> Decimal:
        """
        Dynamically aggregates all principal payments recorded in transactions.
        """
        from apps.ledger.models import Transaction
        result = Transaction.objects.filter(
            target_loan=self,
            transaction_type=Transaction.TransactionType.LOAN_REPAYMENT
        ).aggregate(models.Sum('principal_portion'))['principal_portion__sum']
        return result or Decimal('0.00')

    def get_total_interest_paid(self) -> Decimal:
        """
        Dynamically aggregates all interest payments recorded in transactions.
        """
        from apps.ledger.models import Transaction
        result = Transaction.objects.filter(
            target_loan=self,
            transaction_type=Transaction.TransactionType.LOAN_REPAYMENT
        ).aggregate(models.Sum('interest_portion'))['interest_portion__sum']
        return result or Decimal('0.00')

    def get_remaining_principal(self) -> Decimal:
        """
        Calculates remaining balance dynamically: Principal - Total Principal Paid.
        """
        paid = self.get_total_principal_paid()
        remaining = self.principal_amount - paid
        return max(remaining, Decimal('0.00'))

    def get_next_installment_date(self) -> date | None:
        """
        Determines next due date based on number of payments made so far.
        """
        if self.status in [self.Status.CLOSED, self.Status.PENDING]:
            return None

        from apps.ledger.models import Transaction
        paid_count = Transaction.objects.filter(
            target_loan=self,
            transaction_type=Transaction.TransactionType.LOAN_REPAYMENT
        ).count()

        anchor_date = self.start_date or (self.disbursement_date or date.today())
        next_month_offset = paid_count + 1
        if next_month_offset > self.tenure_months:
            return None

        return anchor_date + relativedelta(months=next_month_offset)

    def check_and_update_status(self):
        """
        Updates loan status if remaining balance reaches 0.
        """
        remaining = self.get_remaining_principal()
        if remaining <= 0 and self.status == self.Status.ACTIVE:
            self.status = self.Status.CLOSED
            self.save(update_fields=['status', 'updated_at'])

    def clean(self):
        if self.principal_amount is not None and self.principal_amount <= 0:
            raise ValidationError({'principal_amount': _("Principal amount must be positive.")})
        if self.interest_rate is not None and self.interest_rate < 0:
            raise ValidationError({'interest_rate': _("Interest rate cannot be negative.")})
        if self.tenure_months is not None and self.tenure_months <= 0:
            raise ValidationError({'tenure_months': _("Tenure must be at least 1 month.")})

    def save(self, *args, **kwargs):
        if not self.emi_amount and self.principal_amount and self.tenure_months:
            self.emi_amount = self.calculate_emi(
                self.principal_amount,
                self.interest_rate,
                self.tenure_months
            )
        self.clean()
        super().save(*args, **kwargs)


class EmergencyAdvance(models.Model):
    """
    Short-term, interest-free funds designed for emergency liquidity.
    Enforces a strict interest_free_until date with grace period and penalty rules.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Approval')
        ACTIVE = 'ACTIVE', _('Active')
        OVERDUE = 'OVERDUE', _('Overdue / Penalty Accruing')
        REPAID = 'REPAID', _('Fully Repaid')

    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='emergency_advances'
    )
    principal_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text=_("Disbursed advance amount")
    )
    disbursement_date = models.DateField(
        default=timezone.now,
        help_text=_("Date advance was disbursed")
    )
    interest_free_until = models.DateField(
        help_text=_("Strict grace period end date. Zero interest applies until this date.")
    )
    penalty_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.00,
        help_text=_("One-time penalty percentage applied if not fully repaid before grace date")
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_advances'
    )
    reason = models.TextField(blank=True, null=True, help_text=_("Emergency justification"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Emergency Advance')
        verbose_name_plural = _('Emergency Advances')
        ordering = ['-created_at']

    def __str__(self):
        return f"Emergency Advance #{self.id} - {self.borrower.username} (${self.principal_amount})"

    # =========================================================================
    # FINANCIAL LOGIC (Fat Model Methods)
    # =========================================================================

    def is_overdue(self, as_of_date: date = None) -> bool:
        """
        Checks whether the advance is past the interest-free grace period
        and still has an outstanding balance.
        """
        check_date = as_of_date or date.today()
        if self.get_remaining_principal() <= 0:
            return False
        return check_date > self.interest_free_until

    def days_remaining(self, as_of_date: date = None) -> int:
        """
        Returns number of days remaining until grace period ends.
        Negative value indicates days overdue.
        """
        check_date = as_of_date or date.today()
        return (self.interest_free_until - check_date).days

    def calculate_penalty(self, as_of_date: date = None) -> Decimal:
        """
        Calculates penalty if past interest_free_until date and not yet settled.
        """
        if not self.is_overdue(as_of_date):
            return Decimal('0.00')

        remaining = self.get_remaining_principal()
        penalty = remaining * (self.penalty_rate / Decimal('100'))
        return penalty.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_total_repaid(self) -> Decimal:
        """
        Dynamically aggregates all repayments made toward this emergency advance.
        """
        from apps.ledger.models import Transaction
        result = Transaction.objects.filter(
            target_emergency=self,
            transaction_type=Transaction.TransactionType.EMERGENCY_REPAYMENT
        ).aggregate(models.Sum('amount'))['amount__sum']
        return result or Decimal('0.00')

    def get_remaining_principal(self) -> Decimal:
        """
        Calculates remaining principal balance before penalties.
        """
        paid = self.get_total_repaid()
        remaining = self.principal_amount - paid
        return max(remaining, Decimal('0.00'))

    def get_total_outstanding(self) -> Decimal:
        """
        Total amount required to close the advance: Remaining Principal + Accrued Penalty.
        """
        return self.get_remaining_principal() + self.calculate_penalty()

    def update_status(self):
        """
        Evaluates current repayment and date to synchronize model status.
        """
        if self.get_remaining_principal() <= 0:
            self.status = self.Status.REPAID
        elif self.is_overdue():
            self.status = self.Status.OVERDUE
        else:
            self.status = self.Status.ACTIVE
        self.save(update_fields=['status', 'updated_at'])
