from rest_framework import serializers
from apps.users.models import User, GlobalSettings


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
            'member_id',
            'phone_number',
            'address',
            'date_of_birth',
            'date_joined',
            'is_active',
            'must_change_password',
        ]
        read_only_fields = ['id', 'member_id', 'date_joined']


class UserCreateUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'password',
            'email',
            'first_name',
            'last_name',
            'role',
            'member_id',
            'phone_number',
            'address',
            'date_of_birth',
            'is_active',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class GlobalSettingsSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.ReadOnlyField(source='updated_by.username')

    class Meta:
        model = GlobalSettings
        fields = [
            'id',
            'organization_name',
            'base_interest_rate',
            'default_emergency_grace_days',
            'default_emergency_penalty_rate',
            'updated_at',
            'updated_by_name'
        ]
        read_only_fields = ['id', 'updated_at', 'updated_by_name']


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, min_length=8, write_only=True)
    confirm_password = serializers.CharField(required=True, min_length=8, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    username_or_email = serializers.CharField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    username_or_email = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8, write_only=True)
    confirm_password = serializers.CharField(required=True, min_length=8, write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})
        return attrs


