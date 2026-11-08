from decimal import Decimal
from rest_framework import serializers

from apps.ledger.models import Account, Transaction, LedgerEntry


class AccountSerializer(serializers.ModelSerializer):
    total_debits = serializers.SerializerMethodField()
    total_credits = serializers.SerializerMethodField()
    net_balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            'id',
            'code',
            'name',
            'account_type',
            'description',
            'is_active',
            'total_debits',
            'total_credits',
            'net_balance'
        ]

    def get_total_debits(self, obj):
        return float(obj.get_total_debits())

    def get_total_credits(self, obj):
        return float(obj.get_total_credits())

    def get_net_balance(self, obj):
        return float(obj.get_net_balance())


class LedgerEntrySerializer(serializers.ModelSerializer):
    account_code = serializers.ReadOnlyField(source='account.code')
    account_name = serializers.ReadOnlyField(source='account.name')

    class Meta:
        model = LedgerEntry
        fields = [
            'id',
            'account',
            'account_code',
            'account_name',
            'entry_type',
            'amount',
            'description',
            'created_at'
        ]


class TransactionSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_member_id = serializers.ReadOnlyField(source='user.member_id')
    created_by_name = serializers.ReadOnlyField(source='created_by.username')
    ledger_entries = LedgerEntrySerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id',
            'transaction_id',
            'user',
            'user_name',
            'user_member_id',
            'transaction_type',
            'target_loan',
            'target_emergency',
            'amount',
            'principal_portion',
            'interest_portion',
            'penalty_portion',
            'payment_method',
            'reference_number',
            'notes',
            'created_by',
            'created_by_name',
            'created_at',
            'ledger_entries'
        ]
        read_only_fields = [
            'id',
            'transaction_id',
            'created_by',
            'created_at',
            'ledger_entries'
        ]

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'id',
            'transaction_id',
            'user',
            'transaction_type',
            'target_loan',
            'target_emergency',
            'amount',
            'principal_portion',
            'interest_portion',
            'penalty_portion',
            'payment_method',
            'reference_number',
            'notes',
        ]
        read_only_fields = ['id', 'transaction_id']

    def validate(self, attrs):
        transaction_type = attrs.get('transaction_type')
        amount = attrs.get('amount')
        target_loan = attrs.get('target_loan')
        target_emergency = attrs.get('target_emergency')

        principal = attrs.get('principal_portion') or Decimal('0.00')
        interest = attrs.get('interest_portion') or Decimal('0.00')
        penalty = attrs.get('penalty_portion') or Decimal('0.00')

        # Auto-portion calculation if operator enters lump-sum payment
        if transaction_type == Transaction.TransactionType.LOAN_REPAYMENT:
            if not target_loan:
                raise serializers.ValidationError({'target_loan': 'Target primary loan is required for repayment.'})

            if principal + interest + penalty == 0:
                # Calculate current month interest on remaining balance
                remaining_principal = target_loan.get_remaining_principal()
                monthly_rate = (target_loan.interest_rate / Decimal('100')) / Decimal('12')
                expected_interest = (remaining_principal * monthly_rate).quantize(Decimal('0.01'))

                if amount <= expected_interest:
                    interest = amount
                    principal = Decimal('0.00')
                else:
                    interest = expected_interest
                    principal = amount - interest

                attrs['principal_portion'] = principal
                attrs['interest_portion'] = interest
                attrs['penalty_portion'] = Decimal('0.00')

        elif transaction_type == Transaction.TransactionType.EMERGENCY_REPAYMENT:
            if not target_emergency:
                raise serializers.ValidationError({'target_emergency': 'Target emergency advance is required.'})

            if principal + penalty == 0:
                accrued_penalty = target_emergency.calculate_penalty()
                if accrued_penalty > 0:
                    penalty = min(amount, accrued_penalty)
                    principal = amount - penalty
                else:
                    penalty = Decimal('0.00')
                    principal = amount

                attrs['principal_portion'] = principal
                attrs['penalty_portion'] = penalty

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['created_by'] = user
        return super().create(validated_data)

