from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.users.models import GlobalSettings
from apps.loans.models import PrimaryLoan, EmergencyAdvance
from apps.ledger.models import Account, Transaction, LedgerEntry
from apps.ledger.reports import TrialBalanceReport

User = get_user_model()


class Command(BaseCommand):
    help = "Seed database with initial SACCOS accounts, users, loans, and sample transactions."

    def handle(self, *args, **options):
        self.stdout.write("Initializing standard chart of accounts...")
        accounts = Account.get_or_create_standard_accounts()
        self.stdout.write(self.style.SUCCESS(f"Initialized {len(accounts)} standard accounts."))

        # Global settings
        settings_obj = GlobalSettings.get_settings()
        self.stdout.write(self.style.SUCCESS(f"Loaded Global Settings: Base Rate {settings_obj.base_interest_rate}%"))

        # 1. Superuser
        superuser, created = User.objects.get_or_create(
            username='superuser',
            defaults={
                'email': 'superuser@saccos.org',
                'first_name': 'Super',
                'last_name': 'Admin',
                'role': User.Role.SUPERUSER,
                'member_id': 'MEM-0001',
                'phone_number': '+1234567890'
            }
        )
        if created:
            superuser.set_password('Admin@123')
            superuser.save()
            self.stdout.write(self.style.SUCCESS("Created Superuser: superuser / Admin@123"))

        # 2. Admin Operator
        admin_op, created = User.objects.get_or_create(
            username='admin_operator',
            defaults={
                'email': 'operator@saccos.org',
                'first_name': 'Financial',
                'last_name': 'Operator',
                'role': User.Role.ADMIN,
                'member_id': 'MEM-0002',
                'phone_number': '+1234567891'
            }
        )
        if created:
            admin_op.set_password('Operator@123')
            admin_op.save()
            self.stdout.write(self.style.SUCCESS("Created Admin: admin_operator / Operator@123"))

        # 3. Members
        john, created = User.objects.get_or_create(
            username='member_john',
            defaults={
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'role': User.Role.MEMBER,
                'member_id': 'MEM-1001',
                'phone_number': '+1234567892',
                'must_change_password': True
            }
        )
        if created:
            john.set_password('Member@123')
            john.must_change_password = True
            john.save()
            self.stdout.write(self.style.SUCCESS("Created Member: member_john / Member@123 (Temporary Password)"))

        jane, created = User.objects.get_or_create(
            username='member_jane',
            defaults={
                'email': 'jane@example.com',
                'first_name': 'Jane',
                'last_name': 'Smith',
                'role': User.Role.MEMBER,
                'member_id': 'MEM-1002',
                'phone_number': '+1234567893',
                'must_change_password': True
            }
        )
        if created:
            jane.set_password('Member@123')
            jane.must_change_password = True
            jane.save()
            self.stdout.write(self.style.SUCCESS("Created Member: member_jane / Member@123"))

        # 4. Sample Transactions if none exist
        if Transaction.objects.count() == 0:
            self.stdout.write("Generating sample transactions...")

            # 4a. John deposits $5,000 into savings
            trx_deposit = Transaction(
                user=john,
                transaction_type=Transaction.TransactionType.DEPOSIT,
                amount=Decimal('5000.00'),
                payment_method=Transaction.PaymentMethod.BANK_TRANSFER,
                reference_number='DEP-2026-001',
                notes='Initial savings deposit from John Doe',
                created_by=admin_op
            )
            trx_deposit.save()

            # 4b. John applies for primary loan of $10,000 at 12% for 12 months
            loan_john = PrimaryLoan.objects.create(
                borrower=john,
                principal_amount=Decimal('10000.00'),
                interest_rate=Decimal('12.00'),
                tenure_months=12,
                start_date=date.today() - relativedelta(months=1),
                approved_by=admin_op,
                status=PrimaryLoan.Status.APPROVED,
                purpose='Home renovation'
            )

            # 4c. Loan Disbursement
            trx_disburse = Transaction(
                user=john,
                transaction_type=Transaction.TransactionType.LOAN_DISBURSEMENT,
                target_loan=loan_john,
                amount=Decimal('10000.00'),
                payment_method=Transaction.PaymentMethod.BANK_TRANSFER,
                reference_number='DISB-2026-001',
                notes='Disbursement of Primary Loan #1',
                created_by=admin_op
            )
            trx_disburse.save()

            # 4d. John repays 1st EMI installment ($888.49)
            # Principal = $788.49, Interest = $100.00 (1% monthly on $10,000)
            trx_repay = Transaction(
                user=john,
                transaction_type=Transaction.TransactionType.LOAN_REPAYMENT,
                target_loan=loan_john,
                amount=Decimal('888.49'),
                principal_portion=Decimal('788.49'),
                interest_portion=Decimal('100.00'),
                penalty_portion=Decimal('0.00'),
                payment_method=Transaction.PaymentMethod.BANK_TRANSFER,
                reference_number='EMI-2026-001',
                notes='1st Monthly EMI installment repayment',
                created_by=admin_op
            )
            trx_repay.save()

            # 4e. Jane takes an Emergency Advance of $1,000
            advance_jane = EmergencyAdvance.objects.create(
                borrower=jane,
                principal_amount=Decimal('1000.00'),
                disbursement_date=date.today() - relativedelta(days=10),
                interest_free_until=date.today() + relativedelta(days=20),
                penalty_rate=Decimal('5.00'),
                approved_by=admin_op,
                status=EmergencyAdvance.Status.ACTIVE,
                reason='Medical emergency'
            )

            # 4f. Emergency advance disbursement transaction
            trx_emergency_disb = Transaction(
                user=jane,
                transaction_type=Transaction.TransactionType.EMERGENCY_DISBURSEMENT,
                target_emergency=advance_jane,
                amount=Decimal('1000.00'),
                payment_method=Transaction.PaymentMethod.CASH,
                reference_number='EMG-2026-001',
                notes='Cash payout for Emergency Advance #1',
                created_by=admin_op
            )
            trx_emergency_disb.save()

            self.stdout.write(self.style.SUCCESS("Sample transactions created successfully."))

        # 5. Verify Trial Balance
        tb = TrialBalanceReport.generate_organization_trial_balance()
        self.stdout.write("--- Organization Trial Balance Verification ---")
        self.stdout.write(f"Total Debits:  ${tb['total_debits']:.2f}")
        self.stdout.write(f"Total Credits: ${tb['total_credits']:.2f}")
        self.stdout.write(f"Difference:    ${tb['net_difference']:.2f}")
        self.stdout.write(f"Is Balanced:   {tb['is_balanced']}")

        if tb['is_balanced']:
            self.stdout.write(self.style.SUCCESS("SUCCESS: Perfect Double-Entry Trial Balance!"))
        else:
            self.stdout.write(self.style.ERROR("ERROR: Trial balance is unbalanced!"))

