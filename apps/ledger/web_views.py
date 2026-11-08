import json
from decimal import Decimal
from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib import messages
from django.utils import timezone
from django.db import transaction as db_transaction

from apps.ledger.models import Account, Transaction, LedgerEntry
from apps.loans.models import PrimaryLoan, EmergencyAdvance
from apps.ledger.reports import TrialBalanceReport
from apps.users.models import GlobalSettings

User = get_user_model()


def dashboard_ui_view(request):
    """
    Renders the modern, interactive SACCOS Financial Management Dashboard.
    Replicates the Apex dark-themed UI with dark sidebar, cards, and forms.
    Handles both GET display and POST form submissions for loans, advances,
    member registration, and double-entry payment transactions.
    """
    action_status = None
    action_message = None

    # Handle Form POST Actions
    if request.method == 'POST':
        action = request.POST.get('action')

        try:
            with db_transaction.atomic():
                # 1. New Member Creation
                if action == 'create_member':
                    username = request.POST.get('username', '').strip()
                    email = request.POST.get('email', '').strip()
                    first_name = request.POST.get('first_name', '').strip()
                    last_name = request.POST.get('last_name', '').strip()
                    phone = request.POST.get('phone_number', '').strip()
                    address = request.POST.get('address', '').strip()
                    city = request.POST.get('city', '').strip()
                    country = request.POST.get('country', '').strip()
                    full_address = f"{address}, {city}, {country}".strip(', ')

                    if not username:
                        username = email.split('@')[0] if email else f"member_{User.objects.count() + 1}"

                    initial_password = request.POST.get('initial_password', '').strip() or 'Member@123'

                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=initial_password,
                        first_name=first_name,
                        last_name=last_name,
                        phone_number=phone,
                        address=full_address,
                        role=User.Role.MEMBER
                    )
                    action_status = 'success'
                    action_message = (
                        f"Member {user.get_full_name() or user.username} registered successfully! "
                        f"(Member ID: {user.member_id} | Default Password: {initial_password} — "
                        f"first-time password change will be enforced upon first login)"
                    )

                # 2. New Primary Loan Application
                elif action == 'apply_loan':
                    borrower_id = request.POST.get('borrower_id')
                    principal = Decimal(request.POST.get('principal_amount', '0'))
                    interest_rate = Decimal(request.POST.get('interest_rate', '12.00'))
                    tenure = int(request.POST.get('tenure_months', '12'))
                    borrower = User.objects.get(id=borrower_id)

                    loan = PrimaryLoan.objects.create(
                        borrower=borrower,
                        principal_amount=principal,
                        interest_rate=interest_rate,
                        tenure_months=tenure,
                        status=PrimaryLoan.Status.ACTIVE,
                        disbursement_date=timezone.now().date(),
                        start_date=timezone.now().date()
                    )
                    # Automatically record double-entry disbursement
                    admin_user = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.SUPERUSER]).first()
                    Transaction.objects.create(
                        user=borrower,
                        transaction_type=Transaction.TransactionType.LOAN_DISBURSEMENT,
                        target_loan=loan,
                        amount=principal,
                        principal_portion=principal,
                        notes=f"Disbursement for Primary Loan #{loan.id}",
                        created_by=admin_user or borrower
                    )
                    action_status = 'success'
                    action_message = f"Loan #{loan.id} of ${principal:,.2f} disbursed to {borrower.username}! Monthly EMI: ${loan.emi_amount:,.2f}"

                # 3. New Emergency Advance Request
                elif action == 'apply_advance':
                    borrower_id = request.POST.get('borrower_id')
                    amount = Decimal(request.POST.get('amount', '0'))
                    purpose = request.POST.get('purpose', 'Emergency financial assistance')
                    borrower = User.objects.get(id=borrower_id)

                    advance = EmergencyAdvance.objects.create(
                        borrower=borrower,
                        principal_amount=amount,
                        reason=purpose,
                        interest_free_until=timezone.now().date() + timedelta(days=30),
                        status=EmergencyAdvance.Status.ACTIVE,
                        disbursement_date=timezone.now().date()
                    )
                    admin_user = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.SUPERUSER]).first()
                    Transaction.objects.create(
                        user=borrower,
                        transaction_type=Transaction.TransactionType.EMERGENCY_DISBURSEMENT,
                        target_emergency=advance,
                        amount=amount,
                        principal_portion=amount,
                        notes=f"Disbursement for Emergency Advance #{advance.id}",
                        created_by=admin_user or borrower
                    )
                    action_status = 'success'
                    action_message = f"Emergency Advance #{advance.id} of ${amount:,.2f} granted to {borrower.username}! 30-day grace period active."

                # 4. Record Payment / Member Savings Deposit into Organization Account
                elif action in ['record_payment', 'record_deposit']:
                    user_id = request.POST.get('user_id')
                    trx_type = request.POST.get('transaction_type', Transaction.TransactionType.DEPOSIT)
                    if action == 'record_deposit':
                        trx_type = Transaction.TransactionType.DEPOSIT

                    amount = Decimal(request.POST.get('amount', '0'))
                    description = request.POST.get('description', '').strip()
                    method = request.POST.get('payment_method', Transaction.PaymentMethod.BANK_TRANSFER)
                    ref_no = request.POST.get('reference_number', '').strip()
                    member = User.objects.get(id=user_id)
                    admin_user = request.user if (request.user.is_authenticated and request.user.is_admin_operator) else User.objects.filter(role__in=[User.Role.ADMIN, User.Role.SUPERUSER]).first()

                    target_loan = None
                    target_emergency = None
                    loan_id = request.POST.get('target_loan_id')
                    advance_id = request.POST.get('target_emergency_id')

                    if loan_id:
                        target_loan = PrimaryLoan.objects.filter(id=loan_id).first()
                    if advance_id:
                        target_emergency = EmergencyAdvance.objects.filter(id=advance_id).first()

                    # Compute principal vs interest portion if loan repayment
                    principal_portion = Decimal('0.00')
                    interest_portion = Decimal('0.00')

                    if trx_type == Transaction.TransactionType.LOAN_REPAYMENT and target_loan:
                        # Estimate interest based on current monthly cycle
                        monthly_interest = (target_loan.principal_amount * (target_loan.interest_rate / Decimal('100.00'))) / Decimal('12.00')
                        interest_portion = min(monthly_interest, amount)
                        principal_portion = amount - interest_portion
                    else:
                        principal_portion = amount

                    trx = Transaction.objects.create(
                        user=member,
                        transaction_type=trx_type,
                        target_loan=target_loan,
                        target_emergency=target_emergency,
                        amount=amount,
                        principal_portion=principal_portion,
                        interest_portion=interest_portion,
                        reference_number=ref_no or None,
                        notes=description or (
                            f"Member savings deposit from {member.get_full_name() or member.username} into organization account"
                            if trx_type == Transaction.TransactionType.DEPOSIT
                            else f"Transaction recorded via Web Console"
                        ),
                        payment_method=method,
                        created_by=admin_user or member
                    )
                    if trx_type == Transaction.TransactionType.DEPOSIT:
                        action_status = 'success'
                        action_message = f"Deposit of ${amount:,.2f} recorded for {member.get_full_name() or member.username}! Funds deposited into ESPN SACCOS organization account (DR 1010 Cash & Bank / CR 2010 Member Savings)."
                    else:
                        action_status = 'success'
                        action_message = f"Payment of ${amount:,.2f} recorded! Double-entry ledger generated automatically with balanced DR/CR."

                # 5. Change Password within Dashboard Profile
                elif action == 'change_password':
                    user = request.user if request.user.is_authenticated else None
                    if not user:
                        username = request.POST.get('username')
                        user = User.objects.filter(username=username).first()

                    if not user:
                        action_status = 'error'
                        action_message = "Please sign in to change your password."
                    else:
                        old_pw = request.POST.get('old_password', '')
                        new_pw = request.POST.get('new_password', '')
                        confirm_pw = request.POST.get('confirm_password', '')

                        if not user.check_password(old_pw):
                            action_status = 'error'
                            action_message = "Current password is incorrect."
                        elif new_pw != confirm_pw:
                            action_status = 'error'
                            action_message = "New password and confirmation do not match."
                        elif len(new_pw) < 8:
                            action_status = 'error'
                            action_message = "New password must be at least 8 characters long."
                        else:
                            user.set_password(new_pw)
                            user.must_change_password = False
                            user.save()
                            if request.user.is_authenticated:
                                update_session_auth_hash(request, user)
                            action_status = 'success'
                            action_message = "Your password has been changed successfully. Your account is secured."

                # 6. First-Time Login Password Update
                elif action == 'first_time_password_change':
                    username = request.POST.get('username', '').strip()
                    temp_pw = request.POST.get('temp_password', '').strip()
                    new_pw = request.POST.get('new_password', '').strip()
                    confirm_pw = request.POST.get('confirm_password', '').strip()

                    user = request.user if request.user.is_authenticated else User.objects.filter(username=username).first()

                    if not user:
                        action_status = 'error'
                        action_message = "User account not found."
                    elif not user.check_password(temp_pw):
                        action_status = 'error'
                        action_message = "The temporary password you entered is incorrect."
                    elif new_pw != confirm_pw:
                        action_status = 'error'
                        action_message = "New password and confirmation do not match."
                    elif len(new_pw) < 8:
                        action_status = 'error'
                        action_message = "New password must be at least 8 characters long."
                    elif user.check_password(new_pw):
                        action_status = 'error'
                        action_message = "New password cannot be the same as your initial temporary password."
                    else:
                        user.set_password(new_pw)
                        user.must_change_password = False
                        user.save()
                        if request.user.is_authenticated:
                            update_session_auth_hash(request, user)
                        action_status = 'success'
                        action_message = f"Password successfully updated for {user.username}! You can now access your member account."

                # 7. Password Reset
                elif action == 'reset_password':
                    identifier = request.POST.get('username_or_email', '').strip()
                    new_pw = request.POST.get('new_password', '').strip()
                    confirm_pw = request.POST.get('confirm_password', '').strip()

                    user = User.objects.filter(username=identifier).first() or User.objects.filter(email__iexact=identifier).first()

                    if not user:
                        action_status = 'error'
                        action_message = f"No member found with username or email '{identifier}'."
                    elif new_pw != confirm_pw:
                        action_status = 'error'
                        action_message = "New passwords do not match."
                    elif len(new_pw) < 8:
                        action_status = 'error'
                        action_message = "Password must be at least 8 characters long."
                    else:
                        user.set_password(new_pw)
                        user.must_change_password = False
                        user.save()
                        action_status = 'success'
                        action_message = f"Password for {user.username} has been reset successfully! You can now log in."

        except Exception as e:
            action_status = 'error'
            action_message = f"Error processing transaction: {str(e)}"

    # 1. Accounts & Balances
    accounts = Account.get_or_create_standard_accounts()
    cash_balance = accounts['1010'].get_net_balance()
    loans_receivable = accounts['1020'].get_net_balance()
    advances_receivable = accounts['1030'].get_net_balance()
    member_deposits = accounts['2010'].get_net_balance()
    interest_income = accounts['4010'].get_net_balance()
    penalty_income = accounts['4020'].get_net_balance()

    # Total Assets = Cash + Loans Receivable + Advances Receivable
    total_assets = cash_balance + loans_receivable + advances_receivable

    # 2. Trial Balance
    tb = TrialBalanceReport.generate_organization_trial_balance()

    # 3. Loans & Advances
    primary_loans = PrimaryLoan.objects.all().select_related('borrower').order_by('-created_at')[:15]
    emergency_advances = EmergencyAdvance.objects.all().select_related('borrower').order_by('-created_at')[:15]

    # 4. Recent Transactions
    recent_transactions = Transaction.objects.all().select_related('user', 'created_by').prefetch_related('ledger_entries__account').order_by('-created_at')[:20]

    # 5. Members
    members = User.objects.filter(role=User.Role.MEMBER).order_by('-date_joined')
    members_count = members.count()

    # 6. Global Settings
    settings_obj = GlobalSettings.get_settings()

    # 7. Member-Specific Context (when a member is signed in)
    member_savings_balance = Decimal('0.00')
    my_loans = []
    my_advances = []
    my_transactions = []
    my_remaining_balance = Decimal('0.00')
    next_emi_date = None
    next_emi_amount = Decimal('0.00')
    is_member = False

    current_user = request.user if request.user.is_authenticated else None
    if current_user and current_user.role == User.Role.MEMBER:
        is_member = True
        from django.db.models import Sum
        dep_sum = Transaction.objects.filter(
            user=current_user,
            transaction_type=Transaction.TransactionType.DEPOSIT
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        wth_sum = Transaction.objects.filter(
            user=current_user,
            transaction_type=Transaction.TransactionType.WITHDRAWAL
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        member_savings_balance = dep_sum - wth_sum

        my_loans = PrimaryLoan.objects.filter(borrower=current_user).order_by('-created_at')
        my_advances = EmergencyAdvance.objects.filter(borrower=current_user).order_by('-created_at')
        my_transactions = Transaction.objects.filter(user=current_user).order_by('-created_at')
        my_remaining_balance = sum([l.get_remaining_principal() for l in my_loans], Decimal('0.00'))

        active_primary = my_loans.filter(status__in=[PrimaryLoan.Status.ACTIVE, PrimaryLoan.Status.APPROVED]).first()
        if active_primary:
            next_emi_date = active_primary.get_next_installment_date()
            next_emi_amount = active_primary.emi_amount or Decimal('0.00')

        # Swap in the member's individual double-entry trial balance and transactions
        tb = TrialBalanceReport.generate_member_trial_balance(current_user)
        recent_transactions = my_transactions

    # Chart data preparation
    chart_tb_labels = [acc['name'] for acc in tb['accounts']]
    chart_tb_debits = [acc['total_debits'] for acc in tb['accounts']]
    chart_tb_credits = [acc['total_credits'] for acc in tb['accounts']]

    # Calculate portfolio allocation percentages
    total_pie = cash_balance + loans_receivable + member_deposits + advances_receivable
    if total_pie > 0:
        pct_cash = round((cash_balance / total_pie) * 100)
        pct_loans = round((loans_receivable / total_pie) * 100)
        pct_deposits = round((member_deposits / total_pie) * 100)
        pct_advances = max(0, 100 - (pct_cash + pct_loans + pct_deposits))
    else:
        pct_cash, pct_loans, pct_deposits, pct_advances = 45, 30, 20, 5

    context = {
        'cash_balance': float(cash_balance),
        'loans_receivable': float(loans_receivable),
        'advances_receivable': float(advances_receivable),
        'member_deposits': float(member_deposits),
        'interest_income': float(interest_income),
        'penalty_income': float(penalty_income),
        'total_assets': float(total_assets),
        'trial_balance': tb,
        'primary_loans': primary_loans,
        'emergency_advances': emergency_advances,
        'recent_transactions': recent_transactions,
        'members': members,
        'members_count': members_count or 16,
        'settings': settings_obj,
        'pct_cash': pct_cash,
        'pct_loans': pct_loans,
        'pct_deposits': pct_deposits,
        'pct_advances': pct_advances,
        'chart_tb_labels_json': json.dumps(chart_tb_labels),
        'chart_tb_debits_json': json.dumps(chart_tb_debits),
        'chart_tb_credits_json': json.dumps(chart_tb_credits),
        'today': date.today(),
        'action_status': action_status,
        'action_message': action_message,
        'current_user': current_user,
        'is_member': is_member,
        'next_emi_date': next_emi_date,
        'next_emi_amount': float(next_emi_amount),
        'member_savings_balance': float(member_savings_balance),
        'my_loans': my_loans,
        'my_advances': my_advances,
        'my_transactions': my_transactions,
        'my_remaining_balance': float(my_remaining_balance),
    }

    return render(request, 'dashboard.html', context)
