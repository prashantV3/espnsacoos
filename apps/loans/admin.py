from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.loans.models import PrimaryLoan, EmergencyAdvance


@admin.register(PrimaryLoan)
class PrimaryLoanAdmin(ModelAdmin):
    list_display = (
        'show_loan_id',
        'show_borrower',
        'principal_amount',
        'interest_rate',
        'tenure_months',
        'emi_amount',
        'show_remaining_principal',
        'show_status_badge',
        'start_date',
        'show_next_emi',
    )
    list_filter = (
        'status',
        'start_date',
        'disbursement_date',
    )
    search_fields = (
        'borrower__username',
        'borrower__member_id',
        'borrower__email',
        'borrower__first_name',
        'borrower__last_name',
        'purpose',
    )
    readonly_fields = ('emi_amount', 'created_at', 'updated_at')
    list_display_links = ('show_loan_id', 'show_borrower')
    autocomplete_fields = ['borrower', 'approved_by']
    list_per_page = 20

    fieldsets = (
        (_('Borrower'), {'fields': ('borrower',)}),
        (_('Loan Terms'), {
            'fields': ('principal_amount', 'interest_rate', 'tenure_months', 'emi_amount'),
        }),
        (_('Timeline'), {'fields': ('start_date', 'disbursement_date')}),
        (_('Status & Approval'), {'fields': ('status', 'approved_by', 'purpose')}),
        (_('Audit'), {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @display(description=_("Loan #"))
    def show_loan_id(self, obj):
        return f"#{obj.id}"

    @display(description=_("Borrower"))
    def show_borrower(self, obj):
        return f"{obj.borrower.get_full_name() or obj.borrower.username} ({obj.borrower.member_id})"

    @display(description=_("Remaining Principal"))
    def show_remaining_principal(self, obj):
        return f"${obj.get_remaining_principal():,.2f}"

    @display(description=_("Status"), label={
        PrimaryLoan.Status.ACTIVE: 'success',
        PrimaryLoan.Status.APPROVED: 'info',
        PrimaryLoan.Status.PENDING: 'warning',
        PrimaryLoan.Status.CLOSED: 'success',
        PrimaryLoan.Status.DEFAULTED: 'danger',
    })
    def show_status_badge(self, obj):
        return obj.status

    @display(description=_("Next EMI Due"))
    def show_next_emi(self, obj):
        d = obj.get_next_installment_date()
        return str(d) if d else "—"


@admin.register(EmergencyAdvance)
class EmergencyAdvanceAdmin(ModelAdmin):
    list_display = (
        'show_advance_id',
        'show_borrower',
        'principal_amount',
        'disbursement_date',
        'interest_free_until',
        'show_days_remaining',
        'show_penalty',
        'show_total_outstanding',
        'show_status_badge',
    )
    list_filter = (
        'status',
        'disbursement_date',
        'interest_free_until',
    )
    search_fields = (
        'borrower__username',
        'borrower__member_id',
        'reason',
    )
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ['borrower', 'approved_by']
    list_per_page = 20

    fieldsets = (
        (_('Borrower'), {'fields': ('borrower',)}),
        (_('Advance Terms'), {'fields': ('principal_amount', 'disbursement_date')}),
        (_('Grace Period & Penalty'), {
            'fields': ('interest_free_until', 'penalty_rate'),
            'description': _('Advance is fully interest-free until this date. After that, the penalty rate applies on the outstanding balance.'),
        }),
        (_('Status & Reason'), {'fields': ('status', 'approved_by', 'reason')}),
        (_('Audit'), {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @display(description=_("Advance #"))
    def show_advance_id(self, obj):
        return f"#{obj.id}"

    @display(description=_("Borrower"))
    def show_borrower(self, obj):
        return f"{obj.borrower.get_full_name() or obj.borrower.username} ({obj.borrower.member_id})"

    @display(description=_("Days Remaining"), label=True)
    def show_days_remaining(self, obj):
        days = obj.days_remaining()
        if days < 0:
            return f"{abs(days)} days OVERDUE"
        elif days == 0:
            return "Due Today"
        return f"{days} days left"

    @display(description=_("Penalty"))
    def show_penalty(self, obj):
        p = obj.calculate_penalty()
        return f"${p:,.2f}" if p > 0 else "—"

    @display(description=_("Total Outstanding"))
    def show_total_outstanding(self, obj):
        return f"${obj.get_total_outstanding():,.2f}"

    @display(description=_("Status"), label={
        EmergencyAdvance.Status.ACTIVE: 'success',
        EmergencyAdvance.Status.OVERDUE: 'danger',
        EmergencyAdvance.Status.REPAID: 'info',
    })
    def show_status_badge(self, obj):
        return obj.status
