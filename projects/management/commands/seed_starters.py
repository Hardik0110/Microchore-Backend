from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import Company, Project, Task


STARTER_BRIEFS = [
    {
        'name': 'Practice 01 · Morning routines',
        'tone': 'lifestyle',
        'keyword': 'morning routine',
        'brief': (
            'Reply to our practice post about morning coffee routines. The keyword '
            '"morning routine" should feel natural in your reply. Friendly, on-topic.'
        ),
        'url': 'https://instagram.com/p/practice-001',
    },
    {
        'name': 'Practice 02 · Product launch',
        'tone': 'product',
        'keyword': 'launch day',
        'brief': (
            'React to a new product launch post. Show genuine enthusiasm. '
            'Keyword: "launch day". Avoid sales-speak.'
        ),
        'url': 'https://instagram.com/p/practice-002',
    },
    {
        'name': 'Practice 03 · Weekend prompt',
        'tone': 'story',
        'keyword': 'weekend',
        'brief': (
            'Reply to a "what is yours?" prompt. Personal voice, conversational. '
            'Keyword: "weekend".'
        ),
        'url': 'https://instagram.com/p/practice-003',
    },
    {
        'name': 'Practice 04 · Hot take',
        'tone': 'disagreement',
        'keyword': 'honestly',
        'brief': (
            'Add nuance to a hot-take post. Disagree gracefully, with reasoning. '
            'Keyword: "honestly".'
        ),
        'url': 'https://instagram.com/p/practice-004',
    },
    {
        'name': 'Practice 05 · Brand reply',
        'tone': 'brand',
        'keyword': 'favorite',
        'brief': (
            'Reply to a brand-style post. Friendly, on-topic, natural keyword integration. '
            'Keyword: "favorite".'
        ),
        'url': 'https://instagram.com/p/practice-005',
    },
]


class Command(BaseCommand):
    help = 'Seeds the five starter practice projects + tasks (idempotent).'

    def handle(self, *args, **options):
        company, created_company = Company.objects.get_or_create(
            name='Microchore Practice',
            defaults={'registration_details': {'note': 'Internal practice projects'}},
        )
        if created_company:
            self.stdout.write(self.style.SUCCESS('Created Company "Microchore Practice".'))
        else:
            self.stdout.write('Company "Microchore Practice" already exists.')

        created = 0
        skipped = 0
        expires = timezone.now() + timedelta(days=7)

        for entry in STARTER_BRIEFS:
            project, was_new = Project.objects.get_or_create(
                company=company,
                name=entry['name'],
                defaults={
                    'is_starter': True,
                    'tone': entry['tone'],
                    'status': 'ACTIVE',
                    'brief_md': entry['brief'],
                    'tone_guidance': '',
                    'target_post_url_default': entry['url'],
                    'keyword_default': entry['keyword'],
                    'pay_rate_per_approved_task': Decimal('0.0'),
                    'payout_cadence': 'WEEKLY',
                    'payout_method_required': 'ANY',
                    'payout_min_threshold': Decimal('5.00'),
                    'terms_md': 'Practice run. No payout, no penalty. Build your voice.',
                    'ai_detection_strictness': 'MEDIUM',
                    'credibility_thresholds': {},
                    'starts_at': timezone.now(),
                    'ends_at': None,
                },
            )

            if not was_new:
                if not project.tasks.exists():
                    Task.objects.create(
                        project=project,
                        status='OPEN',
                        target_post_url=entry['url'],
                        keyword=entry['keyword'],
                        remaining_count=99,
                        total_count=100,
                        expires_at=expires,
                    )
                    self.stdout.write(f"  Added missing task to existing project: {project.name}")
                else:
                    skipped += 1
                continue

            Task.objects.create(
                project=project,
                status='OPEN',
                target_post_url=entry['url'],
                keyword=entry['keyword'],
                remaining_count=99,
                total_count=100,
                expires_at=expires,
            )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"  Created starter project + task: {project.name}"))

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created {created} new starter project(s), skipped {skipped} existing.")
        )
