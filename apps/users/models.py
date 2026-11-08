import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError('The given username must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('role', User.Role.MEMBER)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.SUPERUSER)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERUSER = 'SUPERUSER', _('Superuser')
        ADMIN = 'ADMIN', _('Admin / Financial Operator')
        MEMBER = 'MEMBER', _('Member')

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
        help_text=_('User system role determining permissions')
    )
    member_id = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,
        help_text=_('Unique member identification number (e.g., MEM-1001)')
    )
    phone_number = models.CharField(max_length=25, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text=_('Requires user to set a new password upon first login')
    )

    objects = UserManager()

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-date_joined']

    def __str__(self):
        full = f"{self.first_name} {self.last_name}".strip()
        display = full if full else self.username
        return f"{display} ({self.role})"

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPERUSER or self.is_superuser

    @property
    def is_admin_operator(self):
        return self.role in [self.Role.ADMIN, self.Role.SUPERUSER] or self.is_staff or self.is_superuser

    @property
    def is_member_role(self):
        return self.role == self.Role.MEMBER

    def save(self, *args, **kwargs):
        # Auto-generate member_id if missing and role is MEMBER
        if not self.member_id and self.role == self.Role.MEMBER:
            count = User.objects.count() + 1
            self.member_id = f"MEM-{count:04d}"

        # Require newly created members to set a new password on first login
        if not self.pk and self.role == self.Role.MEMBER:
            self.must_change_password = True

        # Synchronize staff/superuser flags with the role
        if self.role == self.Role.SUPERUSER:
            self.is_superuser = True
            self.is_staff = True
        elif self.role == self.Role.ADMIN:
            self.is_superuser = False
            self.is_staff = True
        elif self.role == self.Role.MEMBER:
            # Prevent non-admin users from retaining staff/superuser flags
            if not kwargs.pop('skip_role_sync', False):
                self.is_superuser = False
                self.is_staff = False

        super().save(*args, **kwargs)


class GlobalSettings(models.Model):
    """
    Global financial settings configured by Superusers:
    - Base interest rates
    - Emergency loan grace periods & penalties
    - Organization information
    """
    organization_name = models.CharField(max_length=150, default="ESPN SACCOS")
    base_interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=12.00,
        help_text=_("Annual base interest rate in percentage (e.g. 12.00 for 12%)")
    )
    default_emergency_grace_days = models.PositiveIntegerField(
        default=30,
        help_text=_("Default grace period in days for interest-free emergency advances")
    )
    default_emergency_penalty_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.00,
        help_text=_("Penalty rate (%) applied if emergency advance is overdue")
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='settings_updates'
    )

    class Meta:
        verbose_name = _('Global Setting')
        verbose_name_plural = _('Global Settings')

    def __str__(self):
        return f"{self.organization_name} Settings (Base Rate: {self.base_interest_rate}%)"

    @classmethod
    def get_settings(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj
