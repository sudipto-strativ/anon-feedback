from django.test import TestCase
from django.contrib.auth.models import User

from feedback.models import UserProfile


class UserProfileSignalTest(TestCase):
    def test_profile_created_on_user_creation(self):
        user = User.objects.create_user(username='alice', password='pass')
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_profile_has_default_employee_role(self):
        user = User.objects.create_user(username='alice', password='pass')
        self.assertEqual(user.profile.role, 'employee')

    def test_profile_not_duplicated_on_user_save(self):
        user = User.objects.create_user(username='alice', password='pass')
        user.first_name = 'Alice'
        user.save()
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)

    def test_each_user_gets_own_profile(self):
        user1 = User.objects.create_user(username='alice', password='pass')
        user2 = User.objects.create_user(username='bob', password='pass')
        self.assertNotEqual(user1.profile.pk, user2.profile.pk)
