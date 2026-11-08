from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from apps.ledger.models import Account, Transaction, LedgerEntry


class LedgerEntryInline(TabularInline):
    model = LedgerEntry
    extra = 0
    can_delete = False
    show_change_link = False
    readonly_fields = ('account', 'show_entry_type', 'amount', 'description', 'created_at')
    fields = ('account', 'show_entry_type', 'amount', 'description', 'created_at')
    verbose_name = _("Journal Entry")
    verbose_name_plural = _("Double-Entry Journal Lines")

    @display(description=_("DR / CR"), label={
        'DEBIT': 'success',
        'CREDIT': 'warning',
    })
    def show_entry_type(self, obj):
        return obj.entry_type

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Account)
class AccountAdmin(ModelAdmin):
    list_display = (
        'code',
        'name',
        'show_account_type',
        'show_net_balance',
        'show_total_debits',
        'show_total_credits',
        'show_active',
        'created_at',
    )
    list_filter = ('account_type', 'is_active')
    search_fields = ('code', 'name')
    readonly_fields = ('created_at',)
    list_per_page = 20

    @display(description=_("Type"), label={
        'ASSET': 'success',
        'LIABILITY': 'warning',
        'EQUITY': 'info',
        'REVENUE': 'success',
        'EXPENSE': 'danger',
    })
    def show_account_type(self, obj):
        return obj.account_type

    @display(description=_("Net Balance"))
    def show_net_balance(self, obj):
        return f"${obj.get_net_balance():,.2f}"

    @display(description=_("Total Debits (DR)"))
    def show_total_debits(self, obj):
        return f"${obj.get_total_debits():,.2f}"

    @display(description=_("Total Credits (CR)"))
    def show_total_credits(self, obj):
        return f"${obj.get_total_credits():,.2f}"

    @display(description=_("Active"), boolean=True)
    def show_active(self, obj):
        return obj.is_active


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    list_display = (
        'show_uuid',
        'show_type_badge',
        'show_member',
        'amount',
        'show_principal',
        'show_interest',
        'show_payment_method',
        'show_created_by',
        'created_at',
    )
    list_filter = ('transaction_type', 'payment_method', 'created_at')
    search_fields = (
        'transaction_id',
        'user__username',
        'user__member_id',
        'reference_number',
    )
    readonly_fields = (
        'transaction_id',
        'created_at',
        'amount',
        'principal_portion',
        'interest_portion',
        'penalty_portion',
        'transaction_type',
        'user',
        'target_loan',
        'target_emergency',
        'payment_method',
        'reference_number',
        'notes',
        'created_by',
    )
    inlines = [LedgerEntryInline]
    list_per_page = 25

    fieldsets = (
        (_('Transaction Identity'), {'fields': ('transaction_id', 'transaction_type', 'user')}),
        (_('Targets'), {'fields': ('target_loan', 'target_emergency')}),
        (_('Amounts'), {'fields': ('amount', 'principal_portion', 'interest_portion', 'penalty_portion')}),
        (_('Payment Info'), {'fields': ('payment_method', 'reference_number', 'notes')}),
        (_('Recorded By'), {'fields': ('created_by', 'created_at')}),
    )

    @display(description=_("Transaction ID"))
    def show_uuid(self, obj):
        return str(obj.transaction_id)[:8] + "..."

    @display(description=_("Type"), label={
        'DEPOSIT': 'success',
        'WITHDRAWAL': 'warning',
        'LOAN_DISBURSEMENT': 'info',
        'LOAN_REPAYMENT': 'info',
        'EMERGENCY_DISBURSEMENT': 'warning',
        'EMERGENCY_REPAYMENT': 'success',
        'PENALTY_PAYMENT': 'danger',
    })
    def show_type_badge(self, obj):
        return obj.transaction_type

    @display(description=_("Member"))
    def show_member(self, obj):
        return f"{obj.user.get_full_name() or obj.user.username} ({obj.user.member_id})"

    @display(description=_("Principal"))
    def show_principal(self, obj):
        return f"${obj.principal_portion:,.2f}" if obj.principal_portion else "—"

    @display(description=_("Interest"))
    def show_interest(self, obj):
        return f"${obj.interest_portion:,.2f}" if obj.interest_portion else "—"

    @display(description=_("Method"), label=True)
    def show_payment_method(self, obj):
        return obj.payment_method

    @display(description=_("Recorded By"))
    def show_created_by(self, obj):
        return obj.created_by.username if obj.created_by else "—"

    def has_change_permission(self, request, obj=None):
        """Immutable: no edits allowed on historical transactions."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Immutable: no deletes allowed on historical transactions."""
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ModelAdmin):
    list_display = (
        'id',
        'show_transaction',
        'account',
        'show_entry_type',
        'amount',
        'description',
        'created_at',
    )
    list_filter = ('entry_type', 'account', 'created_at')
    search_fields = ('account__code', 'account__name', 'description')
    readonly_fields = ('transaction', 'account', 'entry_type', 'amount', 'description', 'created_at')

    @display(description=_("Transaction ID"))
    def show_transaction(self, obj):
        return str(obj.transaction.transaction_id)[:8] + "..."

    @display(description=_("DR / CR"), label={
        'DEBIT': 'success',
        'CREDIT': 'warning',
    })
    def show_entry_type(self, obj):
        return obj.entry_type

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
