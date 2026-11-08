from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.loans.models import PrimaryLoan, EmergencyAdvance
from apps.ledger.models import Transaction, Account

User = get_user_model()


class LoanFinancialLogicTestCase(TestCase):
    def setUp(self):
        Account.get_or_create_standard_accounts()
        self.admin = User.objects.create_user(
            username='admin_test',
            role=User.Role.ADMIN
        )
        self.member = User.objects.create_user(
            username='borrower_test',
            role=User.Role.MEMBER
        )

    def test_emi_calculation_formula(self):
        """
        Verify reducing-balance EMI calculation matches financial annuity formula:
        $10,000 principal at 12% annual rate for 12 months = $888.49 / month
        """
        principal = Decimal('10000.00')
        rate = Decimal('12.00')
        tenure = 12

        emi = PrimaryLoan.calculate_emi(principal, rate, tenure)
        self.assertEqual(emi, Decimal('888.49'))

    def test_zero_interest_loan_emi(self):
        """
        Verify that 0% interest loans divide principal evenly over tenure.
        """
        principal = Decimal('12000.00')
        rate = Decimal('0.00')
        tenure = 12

        emi = PrimaryLoan.calculate_emi(principal, rate, tenure)
        self.assertEqual(emi, Decimal('1000.00'))

    def test_amortization_schedule_reconciliation(self):
        """
        Verify amortization schedule creates 12 monthly payments,
        and closing balance after final payment is exactly 0.00.
        """
        loan = PrimaryLoan.objects.create(
            borrower=self.member,
            principal_amount=Decimal('10000.00'),
            interest_rate=Decimal('12.00'),
            tenure_months=12,
            start_date=date(2026, 1, 1),
            approved_by=self.admin
        )

        schedule = loan.generate_amortization_schedule()
        self.assertEqual(len(schedule), 12)

        # Month 1 interest is 1% of 10,000 = 100.00
        self.assertEqual(schedule[0]['interest_payment'], 100.00)
        self.assertEqual(schedule[0]['principal_payment'], 788.49)

        # Final month closes balance to 0.00
        self.assertEqual(schedule[-1]['closing_balance'], 0.00)

    def test_dynamic_loan_balance_from_transactions(self):
        """
        Balances should not be static; they must be computed dynamically from transactions.
        """
        loan = PrimaryLoan.objects.create(
            borrower=self.member,
            principal_amount=Decimal('5000.00'),
            interest_rate=Decimal('12.00'),
            tenure_months=6,
            approved_by=self.admin
        )

        # Initial disbursement
        Transaction.objects.create(
            user=self.member,
            transaction_type=Transaction.TransactionType.LOAN_DISBURSEMENT,
            target_loan=loan,
            amount=Decimal('5000.00'),
            created_by=self.admin
        )

        self.assertEqual(loan.get_remaining_principal(), Decimal('5000.00'))
        self.assertEqual(loan.get_total_principal_paid(), Decimal('0.00'))
        self.assertEqual(loan.get_total_interest_paid(), Decimal('0.00'))

        # Payment of $1,000 ($950 principal + $50 interest)
        Transaction.objects.create(
            user=self.member,
            transaction_type=Transaction.TransactionType.LOAN_REPAYMENT,
            target_loan=loan,
            amount=Decimal('1000.00'),
            principal_portion=Decimal('950.00'),
            interest_portion=Decimal('50.00'),
            created_by=self.admin
        )

        self.assertEqual(loan.get_total_principal_paid(), Decimal('950.00'))
        self.assertEqual(loan.get_total_interest_paid(), Decimal('50.00'))
        self.assertEqual(loan.get_remaining_principal(), Decimal('4050.00'))

    def test_emergency_advance_grace_period_and_penalty(self):
        """
        Verify interest-free grace period rules:
        - Within grace period: no penalty, not overdue
        - Past grace period: is_overdue=True, penalty applied
        """
        today = date.today()
        # Active advance within grace period (due in 15 days)
        advance = EmergencyAdvance.objects.create(
            borrower=self.member,
            principal_amount=Decimal('1000.00'),
            disbursement_date=today - relativedelta(days=5),
            interest_free_until=today + relativedelta(days=15),
            penalty_rate=Decimal('5.00'),
            approved_by=self.admin
        )

        self.assertFalse(advance.is_overdue())
        self.assertEqual(advance.days_remaining(), 15)
        self.assertEqual(advance.calculate_penalty(), Decimal('0.00'))
        self.assertEqual(advance.get_total_outstanding(), Decimal('1000.00'))

        # Test past grace period
        past_date = today + relativedelta(days=16)
        self.assertTrue(advance.is_overdue(as_of_date=past_date))
        self.assertEqual(advance.days_remaining(as_of_date=past_date), -1)
        # 5% penalty on 1,000 = $50.00
        self.assertEqual(advance.calculate_penalty(as_of_date=past_date), Decimal('50.00'))
