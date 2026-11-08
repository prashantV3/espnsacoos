from decimal import Decimal
from datetime import date
from django.db import models
from django.utils import timezone
from apps.ledger.models import Account, LedgerEntry, Transaction
from apps.loans.models import PrimaryLoan, EmergencyAdvance


class TrialBalanceReport:
    """
    Computes an organization-wide or member-specific Trial Balance report.
    Verifies that total debits equal total credits across the double-entry ledger.
    """

    @classmethod
    def generate_organization_trial_balance(cls, start_date=None, end_date=None) -> dict:
        accounts = Account.objects.all().order_by('code')

        accounts_summary = []
        total_system_debits = Decimal('0.00')
        total_system_credits = Decimal('0.00')

        entries_qs = LedgerEntry.objects.all()
        if start_date:
            entries_qs = entries_qs.filter(created_at__date__gte=start_date)
        if end_date:
            entries_qs = entries_qs.filter(created_at__date__lte=end_date)

        for account in accounts:
            account_entries = entries_qs.filter(account=account)
            debits = account_entries.filter(entry_type=LedgerEntry.EntryType.DEBIT).aggregate(
                models.Sum('amount')
            )['amount__sum'] or Decimal('0.00')

            credits = account_entries.filter(entry_type=LedgerEntry.EntryType.CREDIT).aggregate(
                models.Sum('amount')
            )['amount__sum'] or Decimal('0.00')

            total_system_debits += debits
            total_system_credits += credits

            # Normal accounting balance determination
            if account.account_type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]:
                net = debits - credits
                debit_balance = net if net > 0 else Decimal('0.00')
                credit_balance = abs(net) if net < 0 else Decimal('0.00')
            else:
                net = credits - debits
                debit_balance = abs(net) if net < 0 else Decimal('0.00')
                credit_balance = net if net > 0 else Decimal('0.00')

            accounts_summary.append({
                'account_id': account.id,
                'code': account.code,
                'name': account.name,
                'account_type': account.account_type,
                'total_debits': float(debits),
                'total_credits': float(credits),
                'debit_balance': float(debit_balance),
                'credit_balance': float(credit_balance),
                'net_balance': float(account.get_net_balance())
            })

        net_difference = total_system_debits - total_system_credits
        is_balanced = (net_difference == Decimal('0.00'))

        return {
            'generated_at': timezone.now().isoformat(),
            'is_balanced': is_balanced,
            'total_debits': float(total_system_debits),
            'total_credits': float(total_system_credits),
            'net_difference': float(net_difference),
            'accounts': accounts_summary
        }

    @classmethod
    def generate_member_trial_balance(cls, user) -> dict:
        """
        Computes a member's individual double-entry Trial Balance.
        Aggregates all ledger entries tied to this member's deposits, loan disbursements,
        and repayments, verifying that individual Debits equal Credits.
        """
        accounts = Account.objects.all().order_by('code')
        accounts_summary = []
        total_member_debits = Decimal('0.00')
        total_member_credits = Decimal('0.00')

        entries_qs = LedgerEntry.objects.filter(transaction__user=user)

        for account in accounts:
            account_entries = entries_qs.filter(account=account)
            debits = account_entries.filter(entry_type=LedgerEntry.EntryType.DEBIT).aggregate(
                models.Sum('amount')
            )['amount__sum'] or Decimal('0.00')

            credits = account_entries.filter(entry_type=LedgerEntry.EntryType.CREDIT).aggregate(
                models.Sum('amount')
            )['amount__sum'] or Decimal('0.00')

            if debits > 0 or credits > 0:
                total_member_debits += debits
                total_member_credits += credits

                if account.account_type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]:
                    net = debits - credits
                    debit_balance = net if net > 0 else Decimal('0.00')
                    credit_balance = abs(net) if net < 0 else Decimal('0.00')
                else:
                    net = credits - debits
                    debit_balance = abs(net) if net < 0 else Decimal('0.00')
                    credit_balance = net if net > 0 else Decimal('0.00')

                accounts_summary.append({
                    'account_id': account.id,
                    'code': account.code,
                    'name': account.name,
                    'account_type': account.account_type,
                    'total_debits': float(debits),
                    'total_credits': float(credits),
                    'debit_balance': float(debit_balance),
                    'credit_balance': float(credit_balance),
                    'net_balance': float(debit_balance - credit_balance if account.account_type == Account.AccountType.ASSET else credit_balance - debit_balance)
                })

        net_difference = total_member_debits - total_member_credits
        return {
            'member_id': user.member_id,
            'member_name': user.get_full_name() or user.username,
            'generated_at': timezone.now().isoformat(),
            'is_balanced': (net_difference == Decimal('0.00')),
            'total_debits': float(total_member_debits),
            'total_credits': float(total_member_credits),
            'net_difference': float(net_difference),
            'accounts': accounts_summary
        }

    @classmethod
    def generate_member_financial_summary(cls, user) -> dict:
        """
        Calculates financial standing for a specific member dynamically from transactions.
        """
        user_transactions = Transaction.objects.filter(user=user)

        # 1. Member Deposits balance (Total Deposits - Total Withdrawals)
        deposits = user_transactions.filter(
            transaction_type=Transaction.TransactionType.DEPOSIT
        ).aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0.00')

        withdrawals = user_transactions.filter(
            transaction_type=Transaction.TransactionType.WITHDRAWAL
        ).aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0.00')

        deposit_balance = deposits - withdrawals

        # 2. Total Interest Paid across all primary loans
        total_interest_paid = user_transactions.filter(
            transaction_type=Transaction.TransactionType.LOAN_REPAYMENT
        ).aggregate(models.Sum('interest_portion'))['interest_portion__sum'] or Decimal('0.00')

        # 3. Total Penalties Paid
        total_penalties_paid = user_transactions.filter(
            transaction_type__in=[
                Transaction.TransactionType.LOAN_REPAYMENT,
                Transaction.TransactionType.EMERGENCY_REPAYMENT,
                Transaction.TransactionType.PENALTY_PAYMENT
            ]
        ).aggregate(models.Sum('penalty_portion'))['penalty_portion__sum'] or Decimal('0.00')

        # 4. Active Primary Loans Outstanding
        active_loans = user.primary_loans.filter(status__in=['ACTIVE', 'APPROVED'])
        total_loan_principal_remaining = sum(
            (loan.get_remaining_principal() for loan in active_loans),
            Decimal('0.00')
        )

        # 5. Emergency Advances Outstanding
        active_advances = user.emergency_advances.filter(status__in=['ACTIVE', 'OVERDUE'])
        total_emergency_outstanding = sum(
            (adv.get_total_outstanding() for adv in active_advances),
            Decimal('0.00')
        )

        return {
            'member_id': user.member_id,
            'member_name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'deposit_balance': float(deposit_balance),
            'total_interest_paid': float(total_interest_paid),
            'total_penalties_paid': float(total_penalties_paid),
            'total_loan_principal_remaining': float(total_loan_principal_remaining),
            'total_emergency_outstanding': float(total_emergency_outstanding),
            'net_obligations': float(total_loan_principal_remaining + total_emergency_outstanding - deposit_balance),
        }

    @classmethod
    def generate_balance_sheet(cls, as_of_date=None) -> dict:
        """
        Generates standard Balance Sheet: Assets = Liabilities + Equity
        """
        accounts = Account.objects.all()

        asset_accounts = []
        total_assets = Decimal('0.00')

        liability_accounts = []
        total_liabilities = Decimal('0.00')

        equity_accounts = []
        total_equity_reserves = Decimal('0.00')

        total_revenue = Decimal('0.00')
        total_expenses = Decimal('0.00')

        for acc in accounts:
            balance = acc.get_net_balance()
            acc_info = {
                'code': acc.code,
                'name': acc.name,
                'balance': float(balance)
            }

            if acc.account_type == Account.AccountType.ASSET:
                asset_accounts.append(acc_info)
                total_assets += balance
            elif acc.account_type == Account.AccountType.LIABILITY:
                liability_accounts.append(acc_info)
                total_liabilities += balance
            elif acc.account_type == Account.AccountType.EQUITY:
                equity_accounts.append(acc_info)
                total_equity_reserves += balance
            elif acc.account_type == Account.AccountType.REVENUE:
                total_revenue += balance
            elif acc.account_type == Account.AccountType.EXPENSE:
                total_expenses += balance

        # Current period net surplus belongs to equity
        retained_surplus = total_revenue - total_expenses
        total_equity = total_equity_reserves + retained_surplus

        is_balanced = (total_assets == (total_liabilities + total_equity))

        return {
            'as_of_date': (as_of_date or date.today()).isoformat(),
            'is_balanced': is_balanced,
            'assets': {
                'accounts': asset_accounts,
                'total': float(total_assets)
            },
            'liabilities': {
                'accounts': liability_accounts,
                'total': float(total_liabilities)
            },
            'equity': {
                'accounts': equity_accounts,
                'retained_surplus': float(retained_surplus),
                'total': float(total_equity)
            },
            'total_liabilities_and_equity': float(total_liabilities + total_equity),
            'variance': float(total_assets - (total_liabilities + total_equity))
        }

    @classmethod
    def generate_income_statement(cls, start_date=None, end_date=None) -> dict:
        """
        Generates Income Statement (Profit & Loss): Revenue - Expenses = Net Surplus
        """
        accounts = Account.objects.all()
        revenues = []
        expenses = []
        total_revenue = Decimal('0.00')
        total_expense = Decimal('0.00')

        for acc in accounts:
            balance = acc.get_net_balance()
            if acc.account_type == Account.AccountType.REVENUE:
                revenues.append({'code': acc.code, 'name': acc.name, 'amount': float(balance)})
                total_revenue += balance
            elif acc.account_type == Account.AccountType.EXPENSE:
                expenses.append({'code': acc.code, 'name': acc.name, 'amount': float(balance)})
                total_expense += balance

        net_surplus = total_revenue - total_expense

        return {
            'generated_at': timezone.now().isoformat(),
            'revenues': {
                'items': revenues,
                'total': float(total_revenue)
            },
            'expenses': {
                'items': expenses,
                'total': float(total_expense)
            },
            'net_surplus': float(net_surplus)
        }

    @classmethod
    def generate_portfolio_aging_report(cls) -> dict:
        """
        Evaluates portfolio health and groups active obligations by aging buckets.
        """
        today = date.today()

        # Emergency Advances aging
        advances = EmergencyAdvance.objects.filter(status__in=['ACTIVE', 'OVERDUE'])
        adv_current = Decimal('0.00')
        adv_1_30 = Decimal('0.00')
        adv_31_60 = Decimal('0.00')
        adv_61_plus = Decimal('0.00')

        for adv in advances:
            balance = adv.get_total_outstanding()
            days_overdue = -adv.days_remaining(today)
            if days_overdue <= 0:
                adv_current += balance
            elif days_overdue <= 30:
                adv_1_30 += balance
            elif days_overdue <= 60:
                adv_31_60 += balance
            else:
                adv_61_plus += balance

        # Primary loans portfolio
        loans = PrimaryLoan.objects.filter(status=PrimaryLoan.Status.ACTIVE)
        total_primary_outstanding = sum((l.get_remaining_principal() for l in loans), Decimal('0.00'))

        total_portfolio = total_primary_outstanding + adv_current + adv_1_30 + adv_31_60 + adv_61_plus
        total_overdue = adv_1_30 + adv_31_60 + adv_61_plus

        return {
            'generated_at': timezone.now().isoformat(),
            'total_portfolio_outstanding': float(total_portfolio),
            'primary_loans_active_principal': float(total_primary_outstanding),
            'emergency_advances_aging': {
                'current_within_grace': float(adv_current),
                'overdue_1_to_30_days': float(adv_1_30),
                'overdue_31_to_60_days': float(adv_31_60),
                'overdue_over_60_days': float(adv_61_plus),
                'total_overdue': float(total_overdue)
            },
            'portfolio_at_risk_ratio': float((total_overdue / total_portfolio * 100) if total_portfolio > 0 else 0)
        }
