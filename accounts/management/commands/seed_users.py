from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from reviews.models import ReviewerStats


USERS = [
    {
        'email': 'writer@microchore.test',
        'password': 'WriterPass123!',
        'role': 'USER',
        'handle': 'writer_demo',
        'country': 'AU',
        'starter_approved': 0,
        'description': 'Brand-new writer (no starter approvals yet, real tasks still locked).',
    },
    {
        'email': 'writer.unlocked@microchore.test',
        'password': 'WriterPass123!',
        'role': 'USER',
        'handle': 'writer_unlocked',
        'country': 'AU',
        'starter_approved': 3,
        'description': 'Writer with real_tasks_unlocked == True (3 starter approvals).',
    },
    {
        'email': 'reviewer.t1@microchore.test',
        'password': 'ReviewerPass123!',
        'role': 'REVIEWER',
        'handle': 'reviewer_t1',
        'country': 'AU',
        'reviewer_tier': 'T1',
        'reviewer_multiplier': Decimal('1.0'),
        'description': 'Tier-1 reviewer.',
    },
    {
        'email': 'reviewer.t2@microchore.test',
        'password': 'ReviewerPass123!',
        'role': 'REVIEWER',
        'handle': 'reviewer_t2',
        'country': 'AU',
        'reviewer_tier': 'T2',
        'reviewer_multiplier': Decimal('1.25'),
        'description': 'Tier-2 reviewer.',
    },
    {
        'email': 'reviewer.admin@microchore.test',
        'password': 'ReviewerPass123!',
        'role': 'REVIEWER',
        'handle': 'reviewer_admin',
        'country': 'AU',
        'reviewer_tier': 'ADMIN',
        'reviewer_multiplier': Decimal('1.5'),
        'description': 'Admin reviewer (receives HELD escalations).',
    },
    {
        'email': 'company@microchore.test',
        'password': 'CompanyPass123!',
        'role': 'COMPANY_ADMIN',
        'handle': 'company_admin',
        'country': 'AU',
        'description': 'Company admin (can create projects + tasks).',
    },
    {
        'email': 'platform@microchore.test',
        'password': 'PlatformPass123!',
        'role': 'PLATFORM_ADMIN',
        'handle': 'platform_admin',
        'country': 'AU',
        'is_staff': True,
        'is_superuser': True,
        'description': 'Platform admin / Django superuser (full backstage access).',
    },
]


class Command(BaseCommand):
    help = 'Seed one user per role for local development. Idempotent — re-runs reset passwords + role.'

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        rows = []
        for spec in USERS:
            email = spec['email']
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={'username': email},
            )
            user.username = email
            user.set_password(spec['password'])
            user.role = spec['role']
            user.handle = spec.get('handle', '')
            user.country = spec.get('country', '')
            user.email_verified = True
            user.wizard_step = 'done'
            user.is_active = True
            user.is_staff = spec.get('is_staff', False)
            user.is_superuser = spec.get('is_superuser', False)
            user.starter_approved = spec.get('starter_approved', 0)
            user.save()

            if spec['role'] == 'REVIEWER':
                ReviewerStats.objects.update_or_create(
                    user=user,
                    defaults={
                        'tier': spec['reviewer_tier'],
                        'current_pay_multiplier': spec['reviewer_multiplier'],
                    },
                )

            rows.append((spec['role'], email, spec['password'], spec['description']))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Seeded users:'))
        self.stdout.write('')
        width_role = max(len(r[0]) for r in rows)
        width_email = max(len(r[1]) for r in rows)
        for role, email, password, description in rows:
            self.stdout.write(
                f'  {role.ljust(width_role)}  {email.ljust(width_email)}  {password}'
            )
            self.stdout.write(f'    {self.style.HTTP_INFO(description)}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'These are dev-only credentials. Never seed them in production.'
        ))
