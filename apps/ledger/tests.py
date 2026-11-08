from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.ledger.models import Account, Transaction, LedgerEntry
from apps.ledger.reports import TrialBalanceReport

User = get_user_model()


class DoubleEntryLedgerTestCase(TestCase):
    def setUp(self):
        Account.get_or_create_standard_accounts()
        self.admin = User.objects.create_user(
            username='admin_test',
            role=User.Role.ADMIN
        )
        self.member = User.objects.create_user(
            username='member_test',
            role=User.Role.MEMBER
        )

    def test_transaction_immutability_on_update(self):
        """
        Historical transactions cannot be altered once created.
        """
        trx = Transaction.objects.create(
            user=self.member,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            created_by=self.admin
        )

        trx.amount = Decimal('200.00')
        with self.assertRaises(ValidationError) as ctx:
            trx.save()
        self.assertIn("cannot be modified", str(ctx.exception))

    def test_transaction_immutability_on_delete(self):
        """
        Historical transactions cannot be deleted.
        """
        trx = Transaction.objects.create(
            user=self.member,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            amount=Decimal('500.00'),
            created_by=self.admin
        )

        with self.assertRaises(ValidationError) as ctx:
            trx.delete()
        self.assertIn("cannot be deleted", str(ctx.exception))

    def test_double_entry_balance_per_transaction(self):
        """
        Every transaction must generate balanced Debits and Credits.
        """
        trx = Transaction.objects.create(
            user=self.member,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            amount=Decimal('1500.00'),
            created_by=self.admin
        )

        entries = trx.ledger_entries.all()
        self.assertEqual(entries.count(), 2)

        debit_entry = entries.filter(entry_type=LedgerEntry.EntryType.DEBIT).first()
        credit_entry = entries.filter(entry_type=LedgerEntry.EntryType.CREDIT).first()

        self.assertIsNotNone(debit_entry)
        self.assertIsNotNone(credit_entry)
        self.assertEqual(debit_entry.amount, Decimal('1500.00'))
        self.assertEqual(credit_entry.amount, Decimal('1500.00'))
        self.assertEqual(debit_entry.account.code, '1010')  # Cash & Bank
        self.assertEqual(credit_entry.account.code, '2010') # Member Savings

    def test_trial_balance_reconciliation(self):
        """
        Verify that multiple transactions maintain a perfect zero-difference Trial Balance.
        """
        # Deposit $2,000
        Transaction.objects.create(
            user=self.member,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            amount=Decimal('2000.00'),
            created_by=self.admin
        )

        # Withdrawal $500
        Transaction.objects.create(
            user=self.member,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            amount=Decimal('500.00'),
            created_by=self.admin
        )

        report = TrialBalanceReport.generate_organization_trial_balance()
        self.assertTrue(report['is_balanced'])
        self.assertEqual(report['net_difference'], 0.00)
        self.assertEqual(report['total_debits'], 2500.00)
        self.assertEqual(report['total_credits'], 2500.00)


    def test_web_dashboard_view(self):
        """
        Verify the interactive Web Dashboard loads with status 200.
        """
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ESPN SACCOS")
        self.assertContains(response, "Apex")

    def test_record_member_deposit_via_web_dashboard(self):
        """
        Verify financial operator can record member deposit into organization account via web dashboard.
        """
        self.client.force_login(self.admin)
        response = self.client.post('/', {
            'action': 'record_deposit',
            'user_id': self.member.id,
            'amount': '1250.00',
            'payment_method': 'BANK_TRANSFER',
            'reference_number': 'DEP-TEST-9988',
            'description': 'Monthly mandatory member savings'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deposit of $1,250.00 recorded")

        # Verify transaction and ledger entries
        trx = Transaction.objects.filter(reference_number='DEP-TEST-9988').first()
        self.assertIsNotNone(trx)
        self.assertEqual(trx.amount, Decimal('1250.00'))
        self.assertEqual(trx.transaction_type, Transaction.TransactionType.DEPOSIT)
        self.assertEqual(trx.user, self.member)

        # Verify double-entry DR 1010 and CR 2010
        debit_entry = trx.ledger_entries.filter(entry_type=LedgerEntry.EntryType.DEBIT).first()
        credit_entry = trx.ledger_entries.filter(entry_type=LedgerEntry.EntryType.CREDIT).first()
        self.assertEqual(debit_entry.account.code, '1010')
        self.assertEqual(credit_entry.account.code, '2010')
        self.assertEqual(debit_entry.amount, Decimal('1250.00'))
        self.assertEqual(credit_entry.amount, Decimal('1250.00'))
