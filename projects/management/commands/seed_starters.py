from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import Company, Project, Task


PRACTICE_YOUTUBE_URL = 'https://www.youtube.com/watch?v=6MAzUT1YhWE'


STARTER_BRIEFS = [
    {
        'name': 'Practice 01 · Morning routines',
        'tone': 'lifestyle',
        'keyword': 'morning routine',
        'brief': (
            'Leave a comment on this YouTube video about a slow morning vibe. The keyword '
            '"morning routine" should feel natural in your comment. Friendly, on-topic.'
        ),
        'url': PRACTICE_YOUTUBE_URL,
    },
    {
        'name': 'Practice 02 · Product launch',
        'tone': 'product',
        'keyword': 'launch day',
        'brief': (
            'Comment on this YouTube video as if it were a product launch reaction. '
            'Show genuine enthusiasm. Keyword: "launch day". Avoid sales-speak.'
        ),
        'url': PRACTICE_YOUTUBE_URL,
    },
    {
        'name': 'Practice 03 · Weekend prompt',
        'tone': 'story',
        'keyword': 'weekend',
        'brief': (
            'Reply to the YouTube video with a personal "what is yours?" style comment. '
            'Conversational, first-person. Keyword: "weekend".'
        ),
        'url': PRACTICE_YOUTUBE_URL,
    },
    {
        'name': 'Practice 04 · Hot take',
        'tone': 'disagreement',
        'keyword': 'honestly',
        'brief': (
            'Add nuance to the YouTube video as if responding to a hot take. '
            'Disagree gracefully, with reasoning. Keyword: "honestly".'
        ),
        'url': PRACTICE_YOUTUBE_URL,
    },
    {
        'name': 'Practice 05 · Brand reply',
        'tone': 'brand',
        'keyword': 'favorite',
        'brief': (
            'Comment on this YouTube video in a brand-friendly tone. On-topic, natural '
            'keyword integration. Keyword: "favorite".'
        ),
        'url': PRACTICE_YOUTUBE_URL,
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
