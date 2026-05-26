from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from projects.models import Company, Project, Task
from submissions.models import Claim, Submission
from reviews.models import Review, ReviewerStats, Bundle
from earnings.models import Earning

User = get_user_model()

class SubmissionsAndEarningsApiTests(APITestCase):

    def setUp(self):
        self.writer = User.objects.create_user(
            username='writer@test.com',
            email='writer@test.com',
            password='testpassword123',
            role='USER',
            handle='testwriter'
        )

        self.reviewer1 = User.objects.create_user(
            username='rev1@test.com',
            email='rev1@test.com',
            password='testpassword123',
            role='REVIEWER',
            handle='reviewer1'
        )
        ReviewerStats.objects.create(user=self.reviewer1, tier='T1')

        self.reviewer2 = User.objects.create_user(
            username='rev2@test.com',
            email='rev2@test.com',
            password='testpassword123',
            role='REVIEWER',
            handle='reviewer2'
        )
        ReviewerStats.objects.create(user=self.reviewer2, tier='T1')

        self.reviewer3 = User.objects.create_user(
            username='rev3@test.com',
            email='rev3@test.com',
            password='testpassword123',
            role='REVIEWER',
            handle='reviewer3'
        )
        ReviewerStats.objects.create(user=self.reviewer3, tier='T2')

        self.admin_reviewer = User.objects.create_user(
            username='adminrev@test.com',
            email='adminrev@test.com',
            password='testpassword123',
            role='PLATFORM_ADMIN',
            handle='adminreviewer'
        )
        ReviewerStats.objects.create(user=self.admin_reviewer, tier='ADMIN')

        self.company = Company.objects.create(name='Test Company')

        self.starter_project = Project.objects.create(
            company=self.company,
            name='Starter Project',
            is_starter=True,
            tone='lifestyle',
            status='ACTIVE',
            brief_md='Practice brief',
            pay_rate_per_approved_task=Decimal('0.0000'),
            terms_md='Practice terms'
        )
        self.starter_task = Task.objects.create(
            project=self.starter_project,
            status='OPEN',
            remaining_count=99,
            total_count=99
        )

        self.real_project = Project.objects.create(
            company=self.company,
            name='Real Project',
            is_starter=False,
            tone='product',
            status='ACTIVE',
            brief_md='Real brief',
            pay_rate_per_approved_task=Decimal('2.5000'),
            terms_md='Real terms'
        )
        self.real_task = Task.objects.create(
            project=self.real_project,
            status='OPEN',
            remaining_count=2,
            total_count=2
        )

    def test_task_claim_success(self):
        self.client.force_authenticate(user=self.writer)
        url = f'/api/tasks/{self.real_task.id}/claim/'
        response = self.client.post(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'ACTIVE')

        self.real_task.refresh_from_db()
        self.assertEqual(self.real_task.remaining_count, 1)
        self.assertTrue(Claim.objects.filter(user=self.writer, task=self.real_task, status='ACTIVE').exists())

    def test_task_claim_exhaustion(self):
        self.client.force_authenticate(user=self.writer)
        self.client.post(f'/api/tasks/{self.real_task.id}/claim/')

        other_writer = User.objects.create_user(
            username='writer2@test.com',
            email='writer2@test.com',
            password='testpassword123'
        )
        self.client.force_authenticate(user=other_writer)
        self.client.post(f'/api/tasks/{self.real_task.id}/claim/')

        self.real_task.refresh_from_db()
        self.assertEqual(self.real_task.remaining_count, 0)
        self.assertEqual(self.real_task.status, 'EXHAUSTED')

        third_writer = User.objects.create_user(
            username='writer3@test.com',
            email='writer3@test.com',
            password='testpassword123'
        )
        self.client.force_authenticate(user=third_writer)
        response = self.client.post(f'/api/tasks/{self.real_task.id}/claim/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_double_claim_returns_existing(self):
        self.client.force_authenticate(user=self.writer)
        url = f'/api/tasks/{self.real_task.id}/claim/'
        response1 = self.client.post(url, format='json')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        response2 = self.client.post(url, format='json')
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data['id'], response1.data['id'])

    def test_submission_requires_claim_on_real_task(self):
        self.client.force_authenticate(user=self.writer)
        payload = {
            'taskId': self.real_task.id,
            'text': 'Genuine written comment under review process.',
            'commentUrl': 'https://instagram.com/p/practice-001',
            'pasteCount': 0,
            'charsTyped': 40,
            'pastedChars': 0,
            'elapsedSec': 12,
            'attestationSigned': True
        }
        response = self.client.post('/api/submissions/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('taskId', response.data)

    def test_submission_auto_claims_on_starter_task(self):
        self.client.force_authenticate(user=self.writer)
        payload = {
            'taskId': self.starter_task.id,
            'text': 'Starter task practice run comment.',
            'commentUrl': 'https://instagram.com/p/practice-002',
            'pasteCount': 0,
            'charsTyped': 30,
            'pastedChars': 0,
            'elapsedSec': 10,
            'attestationSigned': True
        }
        response = self.client.post('/api/submissions/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['isStarter'], True)
        self.assertEqual(response.data['status'], 'pending')

    def test_peer_review_aggregation_decisive_approval(self):
        self.client.force_authenticate(user=self.writer)
        self.client.post(f'/api/tasks/{self.real_task.id}/claim/')

        payload = {
            'taskId': self.real_task.id,
            'text': 'A high quality real comments on target handle post.',
            'commentUrl': 'https://instagram.com/p/real-001',
            'pasteCount': 0,
            'charsTyped': 45,
            'pastedChars': 0,
            'elapsedSec': 15,
            'attestationSigned': True
        }
        sub_resp = self.client.post('/api/submissions/', payload, format='json')
        submission_id = sub_resp.data['id']

        self.client.force_authenticate(user=self.reviewer1)
        r1_payload = {
            'rating': 4,
            'justification_text': 'This is a solid keyword integration review justification.',
            'feels_ai_flag': False,
            'time_taken_seconds': 12
        }
        resp1 = self.client.post(f'/api/reviews/submissions/{submission_id}/', r1_payload, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp1.data['status'], 'pending')

        self.client.force_authenticate(user=self.reviewer2)
        r2_payload = {
            'rating': 3,
            'justification_text': 'Meets the expectation, friendly tone and fits right.',
            'feels_ai_flag': False,
            'time_taken_seconds': 10
        }
        resp2 = self.client.post(f'/api/reviews/submissions/{submission_id}/', r2_payload, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.reviewer3)
        r3_payload = {
            'rating': 4,
            'justification_text': 'Outstanding structure and highly contextually relevant.',
            'feels_ai_flag': False,
            'time_taken_seconds': 15
        }
        resp3 = self.client.post(f'/api/reviews/submissions/{submission_id}/', r3_payload, format='json')
        self.assertEqual(resp3.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp3.data['status'], 'approved')
        self.assertEqual(resp3.data['rating'], 3)

        submission = Submission.objects.get(pk=submission_id)
        self.assertAlmostEqual(float(submission.rating_final), 3.67, places=2)
        authoritative_reviews = submission.reviews.filter(is_authoritative=True)
        self.assertEqual(authoritative_reviews.count(), 1)
        self.assertEqual(submission.justification, authoritative_reviews.first().justification_text)

        self.assertTrue(Earning.objects.filter(user=self.writer, submission=submission, amount=Decimal('2.5000'), kind='BASE').exists())

    def test_peer_review_escalation_stdev_held(self):
        self.client.force_authenticate(user=self.writer)
        self.client.post(f'/api/tasks/{self.real_task.id}/claim/')
        payload = {
            'taskId': self.real_task.id,
            'text': 'A polarizing comment leading to review conflicts.',
            'commentUrl': 'https://instagram.com/p/real-002',
            'pasteCount': 0,
            'charsTyped': 40,
            'pastedChars': 0,
            'elapsedSec': 12,
            'attestationSigned': True
        }
        sub_resp = self.client.post('/api/submissions/', payload, format='json')
        submission_id = sub_resp.data['id']

        self.client.force_authenticate(user=self.reviewer1)
        self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 1, 'justification_text': 'Total spam, unrelated comment context.', 'feels_ai_flag': False}, format='json')

        self.client.force_authenticate(user=self.reviewer2)
        self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 3, 'justification_text': 'Meets the expectation, friendly tone and fits right.', 'feels_ai_flag': False}, format='json')

        self.client.force_authenticate(user=self.reviewer3)
        response = self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 5, 'justification_text': 'Outstanding structure and highly contextually relevant.', 'feels_ai_flag': False}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'pending')

        submission = Submission.objects.get(pk=submission_id)
        self.assertEqual(submission.status, 'HELD')

        bundle = Bundle.objects.filter(reviewer=self.admin_reviewer, status='OPEN').first()
        self.assertIsNotNone(bundle)
        self.assertTrue(bundle.submissions.filter(id=submission_id).exists())

    def test_peer_review_escalation_ai_flags(self):
        self.client.force_authenticate(user=self.writer)
        self.client.post(f'/api/tasks/{self.real_task.id}/claim/')
        payload = {
            'taskId': self.real_task.id,
            'text': 'Comment sounding highly like chatbot output.',
            'commentUrl': 'https://instagram.com/p/real-003',
            'pasteCount': 0,
            'charsTyped': 40,
            'pastedChars': 0,
            'elapsedSec': 12,
            'attestationSigned': True
        }
        sub_resp = self.client.post('/api/submissions/', payload, format='json')
        submission_id = sub_resp.data['id']

        self.client.force_authenticate(user=self.reviewer1)
        self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 4, 'justification_text': 'Perfect quality but sounds very robotic.', 'feels_ai_flag': True}, format='json')

        self.client.force_authenticate(user=self.reviewer2)
        self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 4, 'justification_text': 'Perfect quality but sounds very robotic.', 'feels_ai_flag': True}, format='json')

        self.client.force_authenticate(user=self.reviewer3)
        response = self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 4, 'justification_text': 'Perfect quality but sounds very robotic.', 'feels_ai_flag': False}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        submission = Submission.objects.get(pk=submission_id)
        self.assertEqual(submission.status, 'HELD')

    def test_peer_review_starter_onboarding_unlocks(self):
        self.client.force_authenticate(user=self.writer)
        sub_resp = self.client.post('/api/submissions/', {
            'taskId': self.starter_task.id,
            'text': 'Starter run onboarding practice task.',
            'commentUrl': 'https://instagram.com/p/starter',
            'pasteCount': 0,
            'charsTyped': 30,
            'pastedChars': 0,
            'elapsedSec': 10,
            'attestationSigned': True
        }, format='json')
        submission_id = sub_resp.data['id']

        self.client.force_authenticate(user=self.reviewer1)
        self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 4, 'justification_text': 'Perfect keyword integration onboarding practice.'}, format='json')

        self.client.force_authenticate(user=self.reviewer2)
        self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 4, 'justification_text': 'Perfect keyword integration onboarding practice.'}, format='json')

        self.client.force_authenticate(user=self.reviewer3)
        self.client.post(f'/api/reviews/submissions/{submission_id}/', {'rating': 4, 'justification_text': 'Perfect keyword integration onboarding practice.'}, format='json')

        self.writer.refresh_from_db()
        self.assertEqual(self.writer.starter_approved, 1)

    def test_reviewer_authorization_enforced(self):
        self.client.force_authenticate(user=self.writer)
        self.client.post(f'/api/tasks/{self.real_task.id}/claim/')
        sub_resp = self.client.post('/api/submissions/', {
            'taskId': self.real_task.id,
            'text': 'Real task testing commenter submission.',
            'commentUrl': 'https://instagram.com/p/real-004',
            'pasteCount': 0,
            'charsTyped': 40,
            'pastedChars': 0,
            'elapsedSec': 12,
            'attestationSigned': True
        }, format='json')
        submission_id = sub_resp.data['id']

        self.client.force_authenticate(user=self.writer)
        response = self.client.post(f'/api/reviews/submissions/{submission_id}/', {
            'rating': 4,
            'justification_text': 'Trying to bypass authorization review lock.'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
