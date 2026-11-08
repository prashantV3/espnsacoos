import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class Account(models.Model):
    """
    Chart of Accounts for double-entry bookkeeping.
    Guarantees balanced financial statements.
    """
    class AccountType(models.TextChoices):
        ASSET = 'ASSET', _('Asset')
        LIABILITY = 'LIABILITY', _('Liability')
        EQUITY = 'EQUITY', _('Equity')
        REVENUE = 'REVENUE', _('Revenue')
        EXPENSE = 'EXPENSE', _('Expense')

    code = models.CharField(max_length=20, unique=True, help_text=_("Account Code, e.g., '1010'"))
    name = models.CharField(max_length=120, help_text=_("Account Name, e.g., 'Cash and Bank'"))
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Account')
        verbose_name_plural = _('Chart of Accounts')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name} ({self.account_type})"

    def get_total_debits(self) -> Decimal:
        val = self.ledger_entries.filter(entry_type=LedgerEntry.EntryType.DEBIT).aggregate(
            models.Sum('amount')
        )['amount__sum']
        return val or Decimal('0.00')

    def get_total_credits(self) -> Decimal:
        val = self.ledger_entries.filter(entry_type=LedgerEntry.EntryType.CREDIT).aggregate(
            models.Sum('amount')
        )['amount__sum']
        return val or Decimal('0.00')

    def get_net_balance(self) -> Decimal:
        """
        Computes normal balance based on account classification:
        - Asset / Expense: Normal debit balance (Debits - Credits)
        - Liability / Equity / Revenue: Normal credit balance (Credits - Debits)
        """
        debits = self.get_total_debits()
        credits = self.get_total_credits()

        if self.account_type in [self.AccountType.ASSET, self.AccountType.EXPENSE]:
            return debits - credits
        else:
            return credits - debits

    @classmethod
    def get_or_create_standard_accounts(cls):
        """
        Idempotently initializes the fundamental SACCOS chart of accounts.
        """
        standard_accounts = [
            {'code': '1010', 'name': 'Cash and Bank', 'account_type': cls.AccountType.ASSET, 'description': 'Main operational funds & bank holdings'},
            {'code': '1020', 'name': 'Primary Loans Receivable', 'account_type': cls.AccountType.ASSET, 'description': 'Outstanding principal on standard member loans'},
            {'code': '1030', 'name': 'Emergency Advances Receivable', 'account_type': cls.AccountType.ASSET, 'description': 'Outstanding emergency funds extended to members'},
            {'code': '2010', 'name': 'Member Deposits and Savings', 'account_type': cls.AccountType.LIABILITY, 'description': 'Deposited funds owned by members held by SACCOS'},
            {'code': '3010', 'name': 'Retained Earnings and Reserves', 'account_type': cls.AccountType.EQUITY, 'description': 'Accumulated organizational net surplus'},
            {'code': '4010', 'name': 'Interest Income', 'account_type': cls.AccountType.REVENUE, 'description': 'Earned interest on disbursed loans'},
            {'code': '4020', 'name': 'Penalty and Late Fee Income', 'account_type': cls.AccountType.REVENUE, 'description': 'Fines and overdue interest charges'},
        ]
        created = {}
        for acc in standard_accounts:
            obj, _ = cls.objects.get_or_create(
                code=acc['code'],
                defaults={
                    'name': acc['name'],
                    'account_type': acc['account_type'],
                    'description': acc['description']
                }
            )
            created[acc['code']] = obj
        return created


class Transaction(models.Model):
    """
    The Single Source of Truth for all financial deposits, disbursements, and payments.
    Guarantees immutability and generates double-entry LedgerEntry records atomically.
    """
    class TransactionType(models.TextChoices):
        DEPOSIT = 'DEPOSIT', _('Member Savings Deposit')
        WITHDRAWAL = 'WITHDRAWAL', _('Member Savings Withdrawal')
        LOAN_DISBURSEMENT = 'LOAN_DISBURSEMENT', _('Primary Loan Disbursement')
        LOAN_REPAYMENT = 'LOAN_REPAYMENT', _('Primary Loan Installment / Repayment')
        EMERGENCY_DISBURSEMENT = 'EMERGENCY_DISBURSEMENT', _('Emergency Advance Disbursement')
        EMERGENCY_REPAYMENT = 'EMERGENCY_REPAYMENT', _('Emergency Advance Repayment')
        PENALTY_PAYMENT = 'PENALTY_PAYMENT', _('Penalty Fee Payment')

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', _('Cash')
        BANK_TRANSFER = 'BANK_TRANSFER', _('Bank Transfer')
        MOBILE_PAYMENT = 'MOBILE_PAYMENT', _('Mobile Money / Wallet')
        INTERNAL_TRANSFER = 'INTERNAL_TRANSFER', _('Internal Account Transfer')

    transaction_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='financial_transactions',
        help_text=_("Member associated with this financial transaction")
    )
    transaction_type = models.CharField(max_length=30, choices=TransactionType.choices)
    target_loan = models.ForeignKey(
        'loans.PrimaryLoan',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transactions',
        help_text=_("Target primary loan if this transaction affects an interest-bearing loan")
    )
    target_emergency = models.ForeignKey(
        'loans.EmergencyAdvance',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transactions',
        help_text=_("Target emergency advance if this transaction affects an advance")
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text=_("Total transaction amount")
    )
    principal_portion = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("Portion of repayment reducing principal liability")
    )
    interest_portion = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("Portion of repayment recognizing interest revenue")
    )
    penalty_portion = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_("Portion of repayment covering penalties/fines")
    )
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text=_("External reference (bank slip, mobile transaction reference, receipt)")
    )
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='recorded_transactions',
        help_text=_("Financial operator (Admin/Superuser) who recorded this transaction")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Transaction')
        verbose_name_plural = _('Transactions')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} #{str(self.transaction_id)[:8]} - ${self.amount} ({self.user.username})"

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': _("Transaction amount must be strictly greater than 0.")})

        # Validate loan targeting
        if self.transaction_type in [self.TransactionType.LOAN_DISBURSEMENT, self.TransactionType.LOAN_REPAYMENT]:
            if not self.target_loan:
                raise ValidationError({'target_loan': _("A target Primary Loan must be specified for this transaction type.")})
            if self.target_loan.borrower != self.user:
                raise ValidationError({'target_loan': _("Target loan does not belong to the specified member.")})

        # Validate emergency targeting
        if self.transaction_type in [self.TransactionType.EMERGENCY_DISBURSEMENT, self.TransactionType.EMERGENCY_REPAYMENT]:
            if not self.target_emergency:
                raise ValidationError({'target_emergency': _("A target Emergency Advance must be specified for this transaction type.")})
            if self.target_emergency.borrower != self.user:
                raise ValidationError({'target_emergency': _("Target emergency advance does not belong to the specified member.")})

        # Validate portions for repayments
        if self.transaction_type == self.TransactionType.LOAN_REPAYMENT:
            total_portions = self.principal_portion + self.interest_portion + self.penalty_portion
            if total_portions != self.amount:
                # If portions weren't individually broken down, default principal_portion to total amount
                if total_portions == 0:
                    self.principal_portion = self.amount
                else:
                    raise ValidationError(_("Sum of principal, interest, and penalty portions must equal total amount."))

        if self.transaction_type == self.TransactionType.EMERGENCY_REPAYMENT:
            total_portions = self.principal_portion + self.penalty_portion
            if total_portions != self.amount:
                if total_portions == 0:
                    self.principal_portion = self.amount
                else:
                    raise ValidationError(_("Sum of principal and penalty portions must equal total amount."))

    def delete(self, *args, **kwargs):
        raise ValidationError(_("Immutable Ledger: Historical transactions cannot be deleted."))

    def save(self, *args, **kwargs):
        # Strict immutability: Cannot update an already-saved transaction
        if self.pk is not None:
            raise ValidationError(_("Immutable Ledger: Historical transactions cannot be modified."))

        self.full_clean()

        with transaction.atomic():
            super().save(*args, **kwargs)
            self._generate_double_entry_ledger()
            self._update_associated_balances()

    def _generate_double_entry_ledger(self):
        """
        Generates balanced paired LedgerEntry items according to double-entry accounting rules:
        Debits == Credits
        """
        accounts = Account.get_or_create_standard_accounts()
        cash_acc = accounts['1010']
        loan_acc = accounts['1020']
        adv_acc = accounts['1030']
        deposit_acc = accounts['2010']
        interest_rev_acc = accounts['4010']
        penalty_rev_acc = accounts['4020']

        entries = []

        if self.transaction_type == self.TransactionType.DEPOSIT:
            # Member deposits cash into SACCOS savings
            # DR Cash & Bank (+Asset) | CR Member Deposits (+Liability)
            entries.append(LedgerEntry(transaction=self, account=cash_acc, entry_type=LedgerEntry.EntryType.DEBIT, amount=self.amount, description=f"Deposit from {self.user.username}"))
            entries.append(LedgerEntry(transaction=self, account=deposit_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.amount, description=f"Member savings liability for {self.user.username}"))

        elif self.transaction_type == self.TransactionType.WITHDRAWAL:
            # Member withdraws savings
            # DR Member Deposits (-Liability) | CR Cash & Bank (-Asset)
            entries.append(LedgerEntry(transaction=self, account=deposit_acc, entry_type=LedgerEntry.EntryType.DEBIT, amount=self.amount, description=f"Withdrawal by {self.user.username}"))
            entries.append(LedgerEntry(transaction=self, account=cash_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.amount, description=f"Cash payout to {self.user.username}"))

        elif self.transaction_type == self.TransactionType.LOAN_DISBURSEMENT:
            # Disbursing loan to member
            # DR Primary Loans Receivable (+Asset) | CR Cash & Bank (-Asset)
            entries.append(LedgerEntry(transaction=self, account=loan_acc, entry_type=LedgerEntry.EntryType.DEBIT, amount=self.amount, description=f"Loan #{self.target_loan_id} disbursement to {self.user.username}"))
            entries.append(LedgerEntry(transaction=self, account=cash_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.amount, description=f"Loan payout to {self.user.username}"))

        elif self.transaction_type == self.TransactionType.LOAN_REPAYMENT:
            # Member pays loan installment
            # DR Cash & Bank (+Asset) for total amount received
            # CR Primary Loans Receivable (-Asset) for principal portion
            # CR Interest Income (+Revenue) for interest portion
            # CR Penalty Income (+Revenue) for penalty portion (if any)
            entries.append(LedgerEntry(transaction=self, account=cash_acc, entry_type=LedgerEntry.EntryType.DEBIT, amount=self.amount, description=f"Loan #{self.target_loan_id} repayment from {self.user.username}"))

            if self.principal_portion > 0:
                entries.append(LedgerEntry(transaction=self, account=loan_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.principal_portion, description=f"Principal reduction on Loan #{self.target_loan_id}"))

            if self.interest_portion > 0:
                entries.append(LedgerEntry(transaction=self, account=interest_rev_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.interest_portion, description=f"Interest earned on Loan #{self.target_loan_id}"))

            if self.penalty_portion > 0:
                entries.append(LedgerEntry(transaction=self, account=penalty_rev_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.penalty_portion, description=f"Penalty fee on Loan #{self.target_loan_id}"))

        elif self.transaction_type == self.TransactionType.EMERGENCY_DISBURSEMENT:
            # Disbursing emergency advance
            # DR Emergency Advances Receivable (+Asset) | CR Cash & Bank (-Asset)
            entries.append(LedgerEntry(transaction=self, account=adv_acc, entry_type=LedgerEntry.EntryType.DEBIT, amount=self.amount, description=f"Emergency Advance #{self.target_emergency_id} disbursement to {self.user.username}"))
            entries.append(LedgerEntry(transaction=self, account=cash_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.amount, description=f"Emergency cash payout to {self.user.username}"))

        elif self.transaction_type == self.TransactionType.EMERGENCY_REPAYMENT:
            # Repaying emergency advance
            # DR Cash & Bank (+Asset)
            # CR Emergency Advances Receivable (-Asset) for principal portion
            # CR Penalty Income (+Revenue) if penalty was applied
            entries.append(LedgerEntry(transaction=self, account=cash_acc, entry_type=LedgerEntry.EntryType.DEBIT, amount=self.amount, description=f"Emergency Advance #{self.target_emergency_id} repayment from {self.user.username}"))

            if self.principal_portion > 0:
                entries.append(LedgerEntry(transaction=self, account=adv_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.principal_portion, description=f"Emergency advance principal settlement for {self.user.username}"))

            if self.penalty_portion > 0:
                entries.append(LedgerEntry(transaction=self, account=penalty_rev_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.penalty_portion, description=f"Emergency advance penalty settlement for {self.user.username}"))

        elif self.transaction_type == self.TransactionType.PENALTY_PAYMENT:
            # General penalty fee
            entries.append(LedgerEntry(transaction=self, account=cash_acc, entry_type=LedgerEntry.EntryType.DEBIT, amount=self.amount, description=f"Penalty fee paid by {self.user.username}"))
            entries.append(LedgerEntry(transaction=self, account=penalty_rev_acc, entry_type=LedgerEntry.EntryType.CREDIT, amount=self.amount, description=f"Penalty revenue from {self.user.username}"))

        # Bulk create all ledger entries for this transaction
        LedgerEntry.objects.bulk_create(entries)

    def _update_associated_balances(self):
        """
        Updates the statuses of loans or emergency advances if they are fully settled or disbursed.
        """
        if self.target_loan:
            if self.transaction_type == self.TransactionType.LOAN_DISBURSEMENT:
                self.target_loan.status = 'ACTIVE'
                self.target_loan.disbursement_date = self.created_at.date()
                self.target_loan.save(update_fields=['status', 'disbursement_date', 'updated_at'])
            elif self.transaction_type == self.TransactionType.LOAN_REPAYMENT:
                self.target_loan.check_and_update_status()

        if self.target_emergency:
            if self.transaction_type == self.TransactionType.EMERGENCY_DISBURSEMENT:
                self.target_emergency.status = 'ACTIVE'
                self.target_emergency.disbursement_date = self.created_at.date()
                self.target_emergency.save(update_fields=['status', 'disbursement_date', 'updated_at'])
            elif self.transaction_type == self.TransactionType.EMERGENCY_REPAYMENT:
                self.target_emergency.update_status()


class LedgerEntry(models.Model):
    """
    Immutable individual Debit / Credit line generated automatically by Transactions.
    Every financial event creates matching balanced entries.
    """
    class EntryType(models.TextChoices):
        DEBIT = 'DEBIT', _('Debit (DR)')
        CREDIT = 'CREDIT', _('Credit (CR)')

    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.PROTECT,
        related_name='ledger_entries'
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='ledger_entries'
    )
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Ledger Entry')
        verbose_name_plural = _('Ledger Entries')
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"{self.entry_type} ${self.amount} -> {self.account.name}"

    def delete(self, *args, **kwargs):
        raise ValidationError(_("Immutable Ledger: Ledger entries cannot be deleted."))

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError(_("Immutable Ledger: Ledger entries cannot be modified."))
        super().save(*args, **kwargs)
