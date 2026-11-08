from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.ledger.models import Account, Transaction
from apps.loans.models import PrimaryLoan

User = get_user_model()


class AuthAndRBACTestCase(TestCase):
    def setUp(self):
        Account.get_or_create_standard_accounts()
        self.client = APIClient()

        self.superuser = User.objects.create_superuser(
            username='super_user',
            password='SuperPassword123!',
            email='super@saccos.org'
        )

        self.admin = User.objects.create_user(
            username='admin_op',
            password='AdminPassword123!',
            email='admin@saccos.org',
            role=User.Role.ADMIN
        )

        self.member = User.objects.create_user(
            username='member_user',
            password='MemberPassword123!',
            email='member@saccos.org',
            role=User.Role.MEMBER
        )

    def test_dual_jwt_login_cookie_and_json(self):
        """
        Verify login endpoint returns access token in JSON body (for mobile app)
        AND sets HttpOnly cookie (for web client).
        """
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'member_user',
            'password': 'MemberPassword123!'
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)

        # Verify HttpOnly cookies
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)
        self.assertTrue(response.cookies['access_token']['httponly'])
        self.assertTrue(response.cookies['refresh_token']['httponly'])

    def test_mobile_authorization_bearer_header(self):
        """
        Verify future mobile client can authenticate using standard Authorization Bearer header.
        """
        refresh = RefreshToken.for_user(self.member)
        access_token = str(refresh.access_token)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get('/api/v1/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'member_user')

    def test_web_httponly_cookie_authentication(self):
        """
        Verify web client can authenticate via HttpOnly cookie without sending Bearer header.
        """
        refresh = RefreshToken.for_user(self.member)
        access_token = str(refresh.access_token)

        self.client.credentials()  # Clear any headers
        self.client.cookies['access_token'] = access_token

        response = self.client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'member_user')

    def test_member_dashboard_endpoint(self):
        """
        Verify GET /api/v1/dashboard/me/ returns aggregated loan health,
        next EMI date, remaining balance, and personal trial balance for the member.
        """
        # Create loan for member
        loan = PrimaryLoan.objects.create(
            borrower=self.member,
            principal_amount=Decimal('6000.00'),
            interest_rate=Decimal('12.00'),
            tenure_months=6,
            approved_by=self.admin,
            status=PrimaryLoan.Status.ACTIVE
        )

        refresh = RefreshToken.for_user(self.member)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

        response = self.client.get('/api/v1/dashboard/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('member', response.data)
        self.assertIn('summary', response.data)
        self.assertIn('active_primary_loans', response.data)
        self.assertIn('trial_balance_summary', response.data)

        self.assertEqual(response.data['summary']['overall_health'], 'GOOD')
        self.assertEqual(response.data['summary']['primary_loan_balance'], 6000.0)

    def test_post_transactions_rbac(self):
        """
        Admin can record new payments (POST /api/v1/transactions/).
        Regular member is rejected with 403 Forbidden.
        """
        # 1. Member attempt -> Forbidden (403)
        member_token = str(RefreshToken.for_user(self.member).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {member_token}')

        payload = {
            'user': self.member.id,
            'transaction_type': 'DEPOSIT',
            'amount': '500.00',
            'payment_method': 'BANK_TRANSFER'
        }
        res_member = self.client.post('/api/v1/transactions/', payload)
        self.assertEqual(res_member.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin attempt -> Success (201 Created)
        admin_token = str(RefreshToken.for_user(self.admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_token}')

        res_admin = self.client.post('/api/v1/transactions/', payload)
        self.assertEqual(res_admin.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(res_admin.data['amount']), 500.00)

    def test_trial_balance_report_rbac(self):
        """
        Admins/Superusers can access GET /api/v1/reports/trial-balance/.
        Members cannot (403 Forbidden).
        """
        # 1. Member attempt -> 403 Forbidden
        member_token = str(RefreshToken.for_user(self.member).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {member_token}')
        res_member = self.client.get('/api/v1/reports/trial-balance/')
        self.assertEqual(res_member.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin attempt -> 200 OK
        admin_token = str(RefreshToken.for_user(self.admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_token}')
        res_admin = self.client.get('/api/v1/reports/trial-balance/')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        self.assertTrue(res_admin.data['is_balanced'])

    def test_admin_access_restricted_to_admin_and_superuser_only(self):
        """
        Verify /admin/ can only be accessed by Superusers or Admins.
        Any other authenticated user (e.g. Member) is redirected to the Member Dashboard (/).
        """
        from django.test import Client
        web_client = Client()

        # 1. Member visits /admin/ -> redirected to /
        web_client.force_login(self.member)
        res_member = web_client.get('/admin/')
        self.assertEqual(res_member.status_code, 302)
        self.assertEqual(res_member.url, '/')

        # Member visits sub-page /admin/loans/primaryloan/ -> redirected to /
        res_member_sub = web_client.get('/admin/loans/primaryloan/')
        self.assertEqual(res_member_sub.status_code, 302)
        self.assertEqual(res_member_sub.url, '/')

        # 2. Superuser visits /admin/ -> 200 OK
        web_client.force_login(self.superuser)
        res_super = web_client.get('/admin/')
        self.assertEqual(res_super.status_code, 200)

        # 3. Admin operator visits /admin/ -> 200 OK
        web_client.force_login(self.admin)
        res_admin = web_client.get('/admin/')
        self.assertEqual(res_admin.status_code, 200)

    def test_first_time_login_password_change_flow(self):
        """
        Verify that:
        1. When a member is created, must_change_password is True.
        2. Login response flags must_change_password=True.
        3. Member changes password to a new one.
        4. must_change_password becomes False, and member can log in with new password.
        """
        # Create member with temporary password
        new_member = User.objects.create_user(
            username='temp_member',
            password='TempPassword123!',
            email='temp@example.com',
            role=User.Role.MEMBER
        )
        self.assertTrue(new_member.must_change_password)

        # 1. Login with temporary password
        login_res = self.client.post('/api/v1/auth/login/', {
            'username': 'temp_member',
            'password': 'TempPassword123!'
        })
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertTrue(login_res.data['must_change_password'])
        token = login_res.data['access']

        # 2. Try changing with wrong current password -> 400
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        bad_change = self.client.post('/api/v1/auth/change-password/', {
            'old_password': 'WrongPassword!',
            'new_password': 'SecureNewPassword123!',
            'confirm_password': 'SecureNewPassword123!'
        })
        self.assertEqual(bad_change.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Change with correct current password
        good_change = self.client.post('/api/v1/auth/change-password/', {
            'old_password': 'TempPassword123!',
            'new_password': 'SecureNewPassword123!',
            'confirm_password': 'SecureNewPassword123!'
        })
        self.assertEqual(good_change.status_code, status.HTTP_200_OK)
        self.assertFalse(good_change.data['must_change_password'])

        # 4. Verify member now logs in with new password
        new_login = self.client.post('/api/v1/auth/login/', {
            'username': 'temp_member',
            'password': 'SecureNewPassword123!'
        })
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)
        self.assertFalse(new_login.data['must_change_password'])

    def test_password_reset_flow(self):
        """
        Verify password reset endpoint resets password and invalidates temp flag.
        """
        res = self.client.post('/api/v1/auth/reset-password/', {
            'username_or_email': self.member.username,
            'new_password': 'BrandNewPassword123!',
            'confirm_password': 'BrandNewPassword123!'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Login with new reset password
        login_res = self.client.post('/api/v1/auth/login/', {
            'username': self.member.username,
            'password': 'BrandNewPassword123!'
        })
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        self.assertFalse(login_res.data['must_change_password'])
