from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.decorators import display

from apps.users.models import User, GlobalSettings


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = (
        'username',
        'member_id',
        'show_full_name',
        'email',
        'show_role_badge',
        'phone_number',
        'must_change_password',
        'show_active_status',
        'date_joined',
    )
    list_filter = ('role', 'is_active', 'must_change_password', 'date_joined')
    search_fields = ('username', 'member_id', 'email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-date_joined',)
    list_display_links = ('username', 'member_id')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal Info'), {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'address', 'date_of_birth')}),
        (_('SACCOS Role & Membership'), {'fields': ('role', 'member_id', 'must_change_password')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',),
        }),
        (_('Important Dates'), {'fields': ('last_login', 'date_joined'), 'classes': ('collapse',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'role', 'password1', 'password2'),
        }),
        (_('SACCOS Details'), {
            'fields': ('first_name', 'last_name', 'member_id', 'phone_number'),
        }),
    )
    readonly_fields = ('date_joined', 'last_login')

    @display(description=_("Full Name"))
    def show_full_name(self, obj):
        full = f"{obj.first_name} {obj.last_name}".strip()
        return full or "—"

    @display(description=_("Role"), label={
        'SUPERUSER': 'danger',
        'ADMIN': 'warning',
        'MEMBER': 'info',
    })
    def show_role_badge(self, obj):
        return obj.role

    @display(description=_("Active"), boolean=True)
    def show_active_status(self, obj):
        return obj.is_active


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(ModelAdmin):
    list_display = (
        'organization_name',
        'base_interest_rate',
        'default_emergency_grace_days',
        'default_emergency_penalty_rate',
        'show_updated_by',
        'updated_at',
    )
    readonly_fields = ('updated_at',)

    fieldsets = (
        (_('Organization'), {'fields': ('organization_name',)}),
        (_('Interest Rate Configuration'), {
            'fields': ('base_interest_rate',),
            'description': _('Annual base interest rate used for all new primary loan approvals.'),
        }),
        (_('Emergency Advance Defaults'), {
            'fields': ('default_emergency_grace_days', 'default_emergency_penalty_rate'),
        }),
        (_('Audit'), {'fields': ('updated_at', 'updated_by'), 'classes': ('collapse',)}),
    )

    @display(description=_("Last Updated By"))
    def show_updated_by(self, obj):
        return obj.updated_by.username if obj.updated_by else "—"
