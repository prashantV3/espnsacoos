from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from rest_framework import serializers

from apps.loans.models import PrimaryLoan, EmergencyAdvance
from apps.users.models import GlobalSettings


class PrimaryLoanSerializer(serializers.ModelSerializer):
    borrower_name = serializers.SerializerMethodField()
    borrower_member_id = serializers.ReadOnlyField(source='borrower.member_id')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')
    total_principal_paid = serializers.SerializerMethodField()
    total_interest_paid = serializers.SerializerMethodField()
    remaining_principal = serializers.SerializerMethodField()
    next_installment_date = serializers.SerializerMethodField()

    class Meta:
        model = PrimaryLoan
        fields = [
            'id',
            'borrower',
            'borrower_name',
            'borrower_member_id',
            'principal_amount',
            'interest_rate',
            'tenure_months',
            'start_date',
            'disbursement_date',
            'emi_amount',
            'status',
            'approved_by',
            'approved_by_name',
            'purpose',
            'total_principal_paid',
            'total_interest_paid',
            'remaining_principal',
            'next_installment_date',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'emi_amount',
            'disbursement_date',
            'approved_by',
            'created_at',
            'updated_at'
        ]

    def get_borrower_name(self, obj):
        return f"{obj.borrower.first_name} {obj.borrower.last_name}".strip() or obj.borrower.username

    def get_total_principal_paid(self, obj):
        return float(obj.get_total_principal_paid())

    def get_total_interest_paid(self, obj):
        return float(obj.get_total_interest_paid())

    def get_remaining_principal(self, obj):
        return float(obj.get_remaining_principal())

    def get_next_installment_date(self, obj):
        next_date = obj.get_next_installment_date()
        return next_date.isoformat() if next_date else None


class PrimaryLoanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrimaryLoan
        fields = [
            'id',
            'borrower',
            'principal_amount',
            'interest_rate',
            'tenure_months',
            'start_date',
            'purpose',
        ]
        read_only_fields = ['id']

    def validate_interest_rate(self, value):
        if value is None or value <= 0:
            settings_obj = GlobalSettings.get_settings()
            return settings_obj.base_interest_rate
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        # Automatically approve if created by Admin/Superuser
        validated_data['approved_by'] = user
        validated_data['status'] = PrimaryLoan.Status.APPROVED
        return super().create(validated_data)


class EmergencyAdvanceSerializer(serializers.ModelSerializer):
    borrower_name = serializers.SerializerMethodField()
    borrower_member_id = serializers.ReadOnlyField(source='borrower.member_id')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')
    is_overdue = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    accrued_penalty = serializers.SerializerMethodField()
    total_repaid = serializers.SerializerMethodField()
    remaining_principal = serializers.SerializerMethodField()
    total_outstanding = serializers.SerializerMethodField()

    class Meta:
        model = EmergencyAdvance
        fields = [
            'id',
            'borrower',
            'borrower_name',
            'borrower_member_id',
            'principal_amount',
            'disbursement_date',
            'interest_free_until',
            'penalty_rate',
            'status',
            'approved_by',
            'approved_by_name',
            'reason',
            'is_overdue',
            'days_remaining',
            'accrued_penalty',
            'total_repaid',
            'remaining_principal',
            'total_outstanding',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'status', 'approved_by', 'created_at', 'updated_at']

    def get_borrower_name(self, obj):
        return f"{obj.borrower.first_name} {obj.borrower.last_name}".strip() or obj.borrower.username

    def get_is_overdue(self, obj):
        return obj.is_overdue()

    def get_days_remaining(self, obj):
        return obj.days_remaining()

    def get_accrued_penalty(self, obj):
        return float(obj.calculate_penalty())

    def get_total_repaid(self, obj):
        return float(obj.get_total_repaid())

    def get_remaining_principal(self, obj):
        return float(obj.get_remaining_principal())

    def get_total_outstanding(self, obj):
        return float(obj.get_total_outstanding())


class EmergencyAdvanceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyAdvance
        fields = [
            'id',
            'borrower',
            'principal_amount',
            'disbursement_date',
            'interest_free_until',
            'penalty_rate',
            'reason',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        global_settings = GlobalSettings.get_settings()
        disbursement_date = attrs.get('disbursement_date') or date.today()

        if not attrs.get('interest_free_until'):
            # Calculate from default grace days
            attrs['interest_free_until'] = disbursement_date + relativedelta(days=global_settings.default_emergency_grace_days)

        if not attrs.get('penalty_rate'):
            attrs['penalty_rate'] = global_settings.default_emergency_penalty_rate

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['approved_by'] = user
        validated_data['status'] = EmergencyAdvance.Status.ACTIVE
        return super().create(validated_data)



class PrimaryLoanApplySerializer(serializers.ModelSerializer):
    """
    Serializer used by Members to apply for a loan.
    Borrower is automatically set to request.user and status is set to PENDING.
    """
    class Meta:
        model = PrimaryLoan
        fields = [
            'id',
            'principal_amount',
            'tenure_months',
            'purpose',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        user = self.context['request'].user
        global_settings = GlobalSettings.get_settings()
        validated_data['borrower'] = user
        validated_data['interest_rate'] = global_settings.base_interest_rate
        validated_data['status'] = PrimaryLoan.Status.PENDING
        validated_data['start_date'] = date.today()
        return super().create(validated_data)


class EmergencyAdvanceApplySerializer(serializers.ModelSerializer):
    """
    Serializer used by Members to apply for an interest-free emergency advance.
    """
    class Meta:
        model = EmergencyAdvance
        fields = [
            'id',
            'principal_amount',
            'reason',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        user = self.context['request'].user
        global_settings = GlobalSettings.get_settings()
        today = date.today()
        validated_data['borrower'] = user
        validated_data['disbursement_date'] = today
        validated_data['interest_free_until'] = today + relativedelta(days=global_settings.default_emergency_grace_days)
        validated_data['penalty_rate'] = global_settings.default_emergency_penalty_rate
        validated_data['status'] = EmergencyAdvance.Status.PENDING
        return super().create(validated_data)
